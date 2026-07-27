def dfs(value, depth):
    print(f"Current Value: {value}, and Depth: {depth}")
    if value==0:
        print(f"reached target depth: {depth}")
        return
    dfs(value-1, depth+1)

    print(f"Returning from depth: {depth}, and Value: {value}")
dfs(8,0)