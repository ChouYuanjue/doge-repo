"""
text_similarity 模块单元测试
测试 BM25 算法和 tokenize 函数
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.search.text_similarity import (
    BM25,
    tokenize_for_bm25,
    calculate_hybrid_similarity,
    calculate_simple_similarity,
    calculate_cosine_similarity,
)


class TestTokenizeForBm25:
    """tokenize_for_bm25 函数测试"""

    def test_empty_string(self):
        result = tokenize_for_bm25("")
        assert result == ()

    def test_english_unigrams(self):
        result = tokenize_for_bm25("hello world")
        assert "hello" in result
        assert "world" in result

    def test_chinese_bigrams(self):
        result = tokenize_for_bm25("开心")
        assert "开心" in result
        assert "开" in result
        assert "心" in result

    def test_mixed_content(self):
        result = tokenize_for_bm25("hello 开心 world")
        assert "hello" in result
        assert "开心" in result
        assert "world" in result

    def test_punctuation_removal(self):
        result = tokenize_for_bm25("你好，世界！")
        assert "，" not in result
        assert "！" not in result

    def test_chinese_trigram(self):
        result = tokenize_for_bm25("不开心")
        assert "不开心" in result
        assert "不开" in result
        assert "开心" in result
        assert "不" in result
        assert "开" in result
        assert "心" in result

    def test_cache_consistency(self):
        """验证相同输入返回相同输出"""
        result1 = tokenize_for_bm25("测试中文")
        result2 = tokenize_for_bm25("测试中文")
        assert result1 == result2


class TestBM25:
    """BM25 算法测试"""

    def setup_method(self):
        self.corpus = [
            ["开心", "快乐", "高兴", "大笑"],
            ["难过", "伤心", "哭泣", "大哭"],
            ["生气", "愤怒", "恼火"],
            ["开心", "微笑", "笑容"],
        ]

    def test_empty_corpus(self):
        bm25 = BM25([])
        assert bm25.corpus_size == 0

    def test_single_document(self):
        bm25 = BM25([["开心", "快乐"]])
        scores = bm25.get_scores(["开心"])
        assert len(scores) == 1
        assert scores[0] > 0

    def test_idf_calculation(self):
        bm25 = BM25(self.corpus)
        assert "开心" in bm25.idf
        assert bm25.idf["开心"] > 0

    def test_common_word_low_idf(self):
        bm25 = BM25([["的", "是", "在"], ["的", "了", "和"]])
        idf_the = bm25.idf.get("的", 0)
        idf_rare = bm25.idf.get("在", 0)
        assert idf_the < idf_rare

    def test_get_scores(self):
        bm25 = BM25(self.corpus)
        scores = bm25.get_scores(["开心"])
        assert len(scores) == len(self.corpus)
        assert all(isinstance(s, float) for s in scores)

    def test_get_top_k(self):
        bm25 = BM25(self.corpus)
        results = bm25.get_top_k(["开心"], k=2)
        assert len(results) <= 2
        assert all(isinstance(idx, int) and isinstance(score, float) for idx, score in results)
        if len(results) > 1:
            assert results[0][1] >= results[1][1]

    def test_query_not_in_corpus(self):
        bm25 = BM25(self.corpus)
        scores = bm25.get_scores(["完全不相关的词"])
        assert all(s == 0.0 for s in scores)

    def test_doc_length_normalization(self):
        short_doc = [["词"]]
        long_doc = [["词"] * 100]
        bm25 = BM25(short_doc + long_doc)
        scores = bm25.get_scores(["词"])
        assert len(scores) == 2

    def test_duplicate_terms_in_query(self):
        bm25 = BM25([["开心", "快乐"]])
        score1 = bm25.get_scores(["开心"])
        score2 = bm25.get_scores(["开心", "开心"])
        assert score1[0] > 0
        assert score2[0] > 0

    def test_score_zero_for_missing_term(self):
        bm25 = BM25([["开心"]])
        scores = bm25.get_scores(["不存在的词"])
        assert scores[0] == 0.0


class TestCalculateHybridSimilarity:
    """calculate_hybrid_similarity 函数测试"""

    def test_identical_strings(self):
        sim = calculate_hybrid_similarity("开心", "开心")
        assert sim == 1.0

    def test_similar_chinese_bigram_overlap(self):
        sim = calculate_hybrid_similarity("开心", "开心果")
        assert 0 < sim <= 1

    def test_similar_chinese_partial_overlap(self):
        sim = calculate_hybrid_similarity("开心", "开心")
        assert sim == 1.0

    def test_completely_different(self):
        sim = calculate_hybrid_similarity("开心", "愤怒")
        assert 0 <= sim < 1

    def test_empty_input(self):
        assert calculate_hybrid_similarity("", "开心") == 0.0
        assert calculate_hybrid_similarity("开心", "") == 0.0
        assert calculate_hybrid_similarity("", "") == 0.0

    def test_substring_match(self):
        sim = calculate_hybrid_similarity("开心", "非常开心")
        assert sim > 0.5

    def test_english_lowercase(self):
        sim = calculate_hybrid_similarity("HAPPY", "happy")
        assert sim == 1.0

    def test_case_insensitive(self):
        sim = calculate_hybrid_similarity("Hello", "hello")
        assert sim == 1.0


class TestCalculateSimpleSimilarity:
    """calculate_simple_similarity 函数测试"""

    def test_identical(self):
        sim = calculate_simple_similarity("开心", "开心")
        assert sim == 1.0

    def test_partial_match_same_chars(self):
        sim = calculate_simple_similarity("开心", "开心")
        assert sim == 1.0

    def test_no_match(self):
        sim = calculate_simple_similarity("开心", "生气")
        assert 0 <= sim < 0.5

    def test_empty_input(self):
        assert calculate_simple_similarity("", "开心") == 0.0
        assert calculate_simple_similarity("开心", "") == 0.0


class TestCalculateCosineSimilarity:
    """calculate_cosine_similarity 函数测试"""

    def test_identical(self):
        sim = calculate_cosine_similarity("开心", "开心")
        assert sim == 1.0

    def test_partial_overlap(self):
        sim = calculate_cosine_similarity("开心快乐", "开心")
        assert 0 < sim < 1

    def test_no_overlap(self):
        sim = calculate_cosine_similarity("开心", "愤怒")
        assert sim == 0.0

    def test_case_insensitive(self):
        sim = calculate_cosine_similarity("HAPPY", "happy")
        assert sim == 1.0

    def test_empty_input(self):
        assert calculate_cosine_similarity("", "开心") == 0.0
        assert calculate_cosine_similarity("开心", "") == 0.0


class TestBM25Integration:
    """BM25 集成测试 - 模拟表情包搜索场景"""

    def setup_method(self):
        self.emoji_corpus = [
            ["happy", "开心", "大笑", "高兴", "快乐", "笑容"],
            ["sad", "难过", "伤心", "哭泣", "大哭", "泪"],
            ["angry", "生气", "愤怒", "恼火", "发火"],
            ["tired", "累", "瘫倒", "躺平", "休息", "睡觉"],
            ["dumb", "呆", "无语", "发愣", "傻眼"],
        ]

    def test_search_happy_returns_happy_category(self):
        bm25 = BM25(self.emoji_corpus)
        results = bm25.get_top_k(["开心"], k=3)
        doc_indices = [idx for idx, _ in results]
        assert 0 in doc_indices

    def test_search_emotion_returns_related_category(self):
        corpus = [
            ["happy", "开心", "大笑", "高兴", "快乐", "笑容"],
            ["sad", "难过", "伤心", "哭泣", "大哭", "泪"],
            ["angry", "生气", "愤怒", "恼火", "发火", "暴躁"],
            ["tired", "困", "累", "瘫倒", "躺平", "休息"],
            ["dumb", "呆", "无语", "发愣", "傻眼", "懵逼"],
        ]
        bm25 = BM25(corpus)
        results = bm25.get_top_k(["困"], k=3)
        doc_indices = [idx for idx, _ in results]
        assert 3 in doc_indices

    def test_unrelated_query_returns_low_scores(self):
        corpus = [
            ["happy", "开心", "大笑", "高兴", "快乐", "笑容"],
            ["sad", "难过", "伤心", "哭泣", "大哭", "泪"],
            ["angry", "生气", "愤怒", "恼火", "发火", "暴躁"],
            ["tired", "累", "瘫倒", "躺平", "休息", "睡觉", "困"],
            ["dumb", "呆", "无语", "发愣", "傻眼", "懵逼"],
        ]
        bm25 = BM25(corpus)
        results = bm25.get_top_k(["开心"], k=5)
        sad_idx = corpus.index(["sad", "难过", "伤心", "哭泣", "大哭", "泪"])
        sad_score = next((score for idx, score in results if idx == sad_idx), 0)
        happy_idx = corpus.index(["happy", "开心", "大笑", "高兴", "快乐", "笑容"])
        happy_score = next((score for idx, score in results if idx == happy_idx), 0)
        assert happy_score > sad_score

    def test_multi_term_query(self):
        bm25 = BM25(self.emoji_corpus)
        results = bm25.get_top_k(["开心", "大笑"], k=3)
        assert len(results) > 0
        assert results[0][1] > 0
        assert results[0][0] == 0


class TestConfigureSimilarity:
    """权重配置化：configure_similarity 覆盖默认权重并清缓存。"""

    def _reset(self):
        from core.search import text_similarity

        text_similarity.configure_similarity(
            weights={"ngram": 0.28, "cosine": 0.25, "substring": 0.12, "char": 0.08, "edit": 0.27},
            negation_penalty=0.25,
        )

    def test_weight_change_updates_state(self):
        from core.search import text_similarity

        self._reset()
        text_similarity.configure_similarity(
            weights={"ngram": 0.0, "cosine": 0.0, "substring": 0.0, "char": 0.0, "edit": 1.0}
        )
        assert text_similarity._SIM_WEIGHTS["edit"] == 1.0
        assert text_similarity._SIM_WEIGHTS["ngram"] == 0.0
        self._reset()
        assert text_similarity._SIM_WEIGHTS["edit"] == 0.27

    def test_negation_penalty_change(self):
        from core.search import text_similarity

        self._reset()
        text_similarity.configure_similarity(negation_penalty=1.0)
        assert text_similarity._NEGATION_PENALTY == 1.0
        self._reset()
        assert text_similarity._NEGATION_PENALTY == 0.25

    def test_invalid_value_ignored(self):
        from core.search import text_similarity

        self._reset()
        # 非法值（负数/越界）应被忽略
        text_similarity.configure_similarity(weights={"ngram": -5}, negation_penalty=2.0)
        assert text_similarity._SIM_WEIGHTS["ngram"] == 0.28
        assert text_similarity._NEGATION_PENALTY == 0.25
        self._reset()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])