def assign_cluster(vec, index, threshold=0.8):
    hit = index.search(vec, 1)
    return hit.id if hit and hit.score > threshold else index.create(vec)