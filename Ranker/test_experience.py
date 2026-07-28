"""Experience estimation tests — pure functions, no LLM, no network.

Parsing is deterministic, so these assert exact months and years. `TODAY` is
fixed rather than `date.today()` so the open-ended ("Present") cases do not
change their answers as the calendar moves.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Parser.schema import (Depth, Importance, Requirements, Skill,
                           SkillAssessment)
from Ranker.experience import (ExperienceEstimate, estimate_experience,
                               find_ranges)
from Ranker.scoring import ScoringConfig, score_candidate

TODAY = date(2026, 7, 1)


# --------------------------------------------------------------------------
# range parsing


def test_parses_common_date_formats():
    cases = {
        "Engineer 2021 - 2024": 47,          # Jan 2021 -> Dec 2024
        "Jan 2019 – Mar 2022": 38,           # en dash, month precision
        "Engineer 03/2018 - 11/2021": 44,    # numeric months
        "Analyst 2015 to 2019": 59,          # 'to' separator
        "Intern 2017—2018": 23,              # em dash
    }
    for text, months in cases.items():
        found = find_ranges(text, today=TODAY)
        assert len(found) == 1, text
        assert found[0].months == months, f"{text}: {found[0].months} != {months}"


def test_open_ended_ranges_use_the_supplied_reference_date():
    for phrasing in ("March 2020 to Present", "2020 - Current", "2020 - now"):
        found = find_ranges(phrasing, today=TODAY)
        assert len(found) == 1, phrasing
        assert found[0].is_current


def test_reference_date_is_a_parameter_not_the_clock():
    """Scoring is deterministic; an open range must not drift with the calendar."""
    early = find_ranges("2020 - Present", today=date(2021, 1, 1))[0]
    later = find_ranges("2020 - Present", today=date(2026, 1, 1))[0]
    assert later.months > early.months
    # same reference date -> same answer, always
    assert (find_ranges("2020 - Present", today=TODAY)[0].months
            == find_ranges("2020 - Present", today=TODAY)[0].months)


def test_future_and_reversed_ranges_are_dropped():
    assert find_ranges("2030 - 2035", today=TODAY) == []
    assert find_ranges("2024 - 2019", today=TODAY) == []


def test_a_bare_year_is_not_a_range():
    """A graduation year or date of birth must not become employment."""
    assert find_ranges("B.Tech, NIT Trichy, 2018", today=TODAY) == []


# --------------------------------------------------------------------------
# estimation


def test_overlapping_roles_are_merged_not_summed():
    """Concurrent roles, or a promotion split into two entries, must not
    double-count the same calendar time."""
    sections = {"experience": "Engineer 2019 - 2023\nTech Lead 2021 - 2023"}
    est = estimate_experience(sections, today=TODAY)
    # union is 2019-01 .. 2023-12 == 59 months, not 59 + 35
    assert est.years == 4.9
    assert est.method == "date-ranges"
    assert len(est.ranges) == 2


def test_gaps_between_roles_are_not_counted():
    sections = {"experience": "Engineer 2015 - 2016\nEngineer 2022 - 2023"}
    est = estimate_experience(sections, today=TODAY)
    assert est.years == 3.8          # 23 + 23 months; the six-year gap excluded


def test_education_dates_are_excluded():
    """Four years of a degree is not four years of professional experience."""
    sections = {"education": "B.Tech 2014 - 2018", "experience": "Engineer 2022 - 2023"}
    est = estimate_experience(sections, today=TODAY)
    assert est.years == 1.9          # the 2014-2018 degree contributes nothing


def test_unknown_is_none_not_zero():
    """The distinction the scorer depends on: 'we could not tell' must not be
    reported as 'this person has no experience'."""
    est = estimate_experience({"skills": "Python, SQL"}, today=TODAY)
    assert est.years is None
    assert est.known is False
    assert est.warnings


def test_falls_back_to_a_stated_claim_and_flags_it_as_unverified():
    sections = {"summary": "Backend engineer with 7+ years of experience.",
                "experience": "Engineer, Acme Corp\nBuilt things."}
    est = estimate_experience(sections, today=TODAY)
    assert est.years == 7.0
    assert est.method == "claimed"
    assert any("unverified" in w for w in est.warnings)


def test_claim_wildly_exceeding_dated_roles_is_flagged():
    sections = {"summary": "10+ years of experience",
                "experience": "Engineer 2023 - 2024"}
    est = estimate_experience(sections, today=TODAY)
    assert est.method == "date-ranges"     # computed wins over claimed
    assert est.claimed_years == 10.0
    assert any("verify manually" in w for w in est.warnings)


# --------------------------------------------------------------------------
# effect on scoring


REQ_NO_YEARS = Requirements(
    role_title="Backend Engineer",
    mandatory_skills=[Skill("Python", Importance.MANDATORY)],
    preferred_skills=[Skill("Terraform", Importance.PREFERRED)])

REQ_5_YEARS = Requirements(
    role_title="Senior Backend Engineer",
    mandatory_skills=[Skill("Python", Importance.MANDATORY)],
    preferred_skills=[Skill("Terraform", Importance.PREFERRED)],
    min_years_experience=5)

ASSESSMENTS = [
    SkillAssessment("Python", Importance.MANDATORY, Depth.STRONG, "evidence"),
    SkillAssessment("Terraform", Importance.PREFERRED, Depth.STRONG, "evidence"),
]


def test_no_stated_minimum_leaves_the_scale_untouched():
    """Backward compatibility: a JD without a years requirement scores exactly
    as it did before experience existed."""
    got = score_candidate(REQ_NO_YEARS, ASSESSMENTS,
                          experience=ExperienceEstimate(years=12.0,
                                                        method="date-ranges"))
    assert got.score == 100.0
    assert [c.label for c in got.components] == ["Mandatory skills",
                                                 "Preferred skills"]


def test_meeting_the_bar_still_scores_full_marks():
    got = score_candidate(REQ_5_YEARS, ASSESSMENTS,
                          experience=ExperienceEstimate(years=6.0,
                                                        method="date-ranges"))
    assert got.score == 100.0
    assert len(got.components) == 3


def test_falling_short_costs_proportionally():
    got = score_candidate(REQ_5_YEARS, ASSESSMENTS,
                          experience=ExperienceEstimate(years=2.0,
                                                        method="date-ranges"))
    # skills full at 85, experience 2/5 of 15 == 6.0
    assert got.score == 91.0
    assert any("2 of 5 years" in c.detail for c in got.components)
    assert any("2 years experience" in m for m in got.missing_or_weak)


def test_tolerance_absorbs_year_only_parsing_noise():
    """4.6 years against a 5-year bar is inside the +/- 6 month uncertainty of
    year-only ranges, so it must not fall off a cliff."""
    got = score_candidate(REQ_5_YEARS, ASSESSMENTS,
                          experience=ExperienceEstimate(years=4.6,
                                                        method="date-ranges"))
    assert got.score == 100.0


def test_surplus_experience_earns_no_bonus():
    five = score_candidate(REQ_5_YEARS, ASSESSMENTS,
                           experience=ExperienceEstimate(years=5.0,
                                                         method="date-ranges"))
    twenty = score_candidate(REQ_5_YEARS, ASSESSMENTS,
                             experience=ExperienceEstimate(years=20.0,
                                                           method="date-ranges"))
    assert five.score == twenty.score == 100.0


def test_unreadable_experience_flags_rather_than_penalises():
    """A resume we could not date is a document problem, not a candidate
    deficiency — the weight is never carved out, and a human is told to look."""
    got = score_candidate(REQ_5_YEARS, ASSESSMENTS,
                          experience=ExperienceEstimate())     # years is None
    assert got.score == 100.0
    assert len(got.components) == 2
    assert any("no dates could be read" in f for f in got.flags)


def test_omitting_the_estimate_entirely_is_safe():
    got = score_candidate(REQ_5_YEARS, ASSESSMENTS)
    assert got.score == 100.0
    assert any("review manually" in f for f in got.flags)


def test_self_reported_years_are_marked_in_the_explanation():
    got = score_candidate(REQ_5_YEARS, ASSESSMENTS,
                          experience=ExperienceEstimate(years=6.0,
                                                        method="claimed"))
    assert got.score == 100.0
    assert any("self-reported" in c.detail for c in got.components)


def test_scoring_stays_deterministic():
    est = ExperienceEstimate(years=3.0, method="date-ranges")
    a = score_candidate(REQ_5_YEARS, ASSESSMENTS, experience=est)
    b = score_candidate(REQ_5_YEARS, ASSESSMENTS, experience=est)
    assert a.score == b.score
    assert a.explanation == b.explanation