"""Semantic grouping of intent candidates (cosine similarity, HDBSCAN with fallbacks)."""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import HDBSCAN, AgglomerativeClustering

HDBSCAN_MIN_POINTS = 5


@dataclass
class Cluster:
    members: list[int]
    cohesion: float
    method: str


@dataclass
class ClusteringResult:
    clusters: list[Cluster] = field(default_factory=list)
    outliers: list[int] = field(default_factory=list)
    method: str = "none"


def similarity_matrix(X: np.ndarray) -> np.ndarray:
    return np.clip(X @ X.T, -1.0, 1.0)


def cohesion(S: np.ndarray, idx: list[int]) -> float:
    if len(idx) < 2:
        return 1.0
    sub = S[np.ix_(idx, idx)]
    n = len(idx)
    return float((sub.sum() - np.trace(sub)) / (n * (n - 1)))


def _agglomerative(D: np.ndarray, threshold: float) -> np.ndarray:
    if D.shape[0] < 2:
        return np.array([-1] * D.shape[0])
    model = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average",
                                    distance_threshold=1.0 - threshold)
    labels = model.fit_predict(D)
    # singletons are outliers, not clusters
    counts = np.bincount(labels)
    return np.array([lab if counts[lab] >= 2 else -1 for lab in labels])


def _hdbscan(D: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = HDBSCAN(min_cluster_size=2, min_samples=1, metric="precomputed", allow_single_cluster=True,
                        copy=True)
        return model.fit_predict(D.astype(np.float64))


def cluster_candidates(X: np.ndarray, cluster_threshold: float) -> ClusteringResult:
    """Group unit vectors. Every cluster has average pairwise similarity >= cluster_threshold.

    HDBSCAN is used when enough points exist; tiny or degenerate sets fall back to
    average-linkage agglomerative clustering with the same cohesion threshold.
    Candidates that do not fit anywhere stay outliers (never forced into a cluster).
    """
    n = X.shape[0]
    if n == 0:
        return ClusteringResult()
    if n == 1:
        return ClusteringResult(outliers=[0], method="single")
    S = similarity_matrix(X)
    D = np.clip(1.0 - S, 0.0, 2.0)
    np.fill_diagonal(D, 0.0)

    if n >= HDBSCAN_MIN_POINTS:
        try:
            labels = _hdbscan(D)
            method = "hdbscan"
        except Exception:  # pragma: no cover - defensive
            labels = np.full(n, -1)
            method = "hdbscan_failed"
        if (labels == -1).all():
            labels = _agglomerative(D, cluster_threshold)
            method = "agglomerative_fallback"
    else:
        labels = _agglomerative(D, cluster_threshold)
        method = "agglomerative_small_set"

    result = ClusteringResult(method=method)
    assigned: set[int] = set()
    for lab in sorted(set(labels.tolist()) - {-1}):
        idx = [i for i in range(n) if labels[i] == lab]
        coh = cohesion(S, idx)
        if coh >= cluster_threshold:
            result.clusters.append(Cluster(idx, coh, method))
            assigned.update(idx)
            continue
        # loose density cluster: refine with the stricter cohesion criterion
        sub_labels = _agglomerative(D[np.ix_(idx, idx)], cluster_threshold)
        for sl in sorted(set(sub_labels.tolist()) - {-1}):
            sub = [idx[j] for j in range(len(idx)) if sub_labels[j] == sl]
            result.clusters.append(Cluster(sub, cohesion(S, sub), method + "+cohesion_split"))
            assigned.update(sub)
    result.outliers = [i for i in range(n) if i not in assigned]
    result.clusters.sort(key=lambda c: -len(c.members))
    return result


def best_matches(vec: np.ndarray, centroids: dict[str, np.ndarray], top: int = 3) -> list[tuple[str, float]]:
    if not centroids:
        return []
    ids = list(centroids)
    M = np.stack([centroids[i] for i in ids])
    sims = M @ vec
    order = np.argsort(-sims)[:top]
    return [(ids[i], float(sims[i])) for i in order]


def find_subclusters(X: np.ndarray, cluster_threshold: float, separation: float, min_size: int = 3) -> list[list[int]] | None:
    """Detect whether a category contains two or more clearly separated sub-groups (split candidate)."""
    if X.shape[0] < 2 * min_size:
        return None
    res = cluster_candidates(X, min(0.95, cluster_threshold + 0.05))
    groups = [c.members for c in res.clusters if len(c.members) >= min_size]
    if len(groups) < 2:
        return None
    cents = [X[g].mean(axis=0) for g in groups]
    cents = [c / (np.linalg.norm(c) or 1.0) for c in cents]
    for i in range(len(cents)):
        for j in range(i + 1, len(cents)):
            if float(cents[i] @ cents[j]) >= separation:
                return None
    return groups


def near_duplicates(X: np.ndarray, threshold: float = 0.95) -> list[tuple[int, int, float]]:
    S = similarity_matrix(X)
    out = []
    for i in range(X.shape[0]):
        for j in range(i + 1, X.shape[0]):
            if S[i, j] >= threshold:
                out.append((i, j, float(S[i, j])))
    return out
