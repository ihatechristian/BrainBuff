# cluster_questions.py
import json
import os
import re
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans


def clean_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s\.\-\+\/\(\)\$]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def label_cluster(top_terms):
    """
    Small heuristic labeler (you can customize).
    """
    terms = set(top_terms)

    if {"tens", "thousands", "hundreds", "digit", "place", "value"} & terms:
        return "number_sense_place_value"
    if {"multiply", "times", "product", "boxes"} & terms:
        return "multiplication_facts_models"
    if {"divide", "remainder", "carton", "each"} & terms:
        return "division_word_remainder"
    if {"ratio", "times", "altogether", "parts"} & terms:
        return "ratio_word_problem"
    if {"fraction", "half", "eighths"} & terms:
        return "fraction_equivalence"
    if {"mass", "kg", "g", "grams"} & terms:
        return "measurement_mass"

    # fallback generic
    return "cluster_" + "_".join(list(top_terms)[:2])


def main():
    in_path = "questions.json"
    out_path = "questions_with_clusters.json"

    if not os.path.exists(in_path):
        raise FileNotFoundError(f"Could not find {in_path} in: {os.getcwd()}")

    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build text features
    docs = []
    for q in data:
        topic = str(q.get("topic", ""))
        question = str(q.get("question", ""))
        # include topic + question (helps a lot)
        docs.append(clean_text(f"{topic}. {question}"))

    # Choose K (you can tune)
    K = 6  # good starting point for PSLE bank; change as you grow
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    X = vectorizer.fit_transform(docs)

    model = KMeans(n_clusters=K, random_state=42, n_init="auto")
    labels = model.fit_predict(X)

    # Find top terms per cluster to auto-label
    terms = vectorizer.get_feature_names_out()
    centroids = model.cluster_centers_
    cluster_top_terms = {}
    for k in range(K):
        top_idx = centroids[k].argsort()[::-1][:8]
        top_terms = [terms[i] for i in top_idx]
        cluster_top_terms[k] = top_terms

    # Assign cluster fields
    for i, q in enumerate(data):
        cid = int(labels[i])
        top_terms = cluster_top_terms[cid]
        q["cluster_id"] = cid
        q["question_cluster"] = label_cluster(top_terms)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote {out_path}")
    print("Cluster summaries:")
    counts = Counter(labels)
    for cid, n in sorted(counts.items(), key=lambda x: x[0]):
        print(f"  cluster {cid}: n={n} top_terms={cluster_top_terms[cid][:6]}")


if __name__ == "__main__":
    main()
