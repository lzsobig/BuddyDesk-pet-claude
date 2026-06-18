"""
SenseVoice ASR — 轻量本地语音识别（P3-6）。

不依赖 torch / funasr，直接用 onnxruntime + kaldi_native_fbank。
模型：阿里达摩院 SenseVoice-Small，本地 ~230MB ONNX。

支持：
- 中文/英文/日文/韩文/粤语（language id 区分）
- CPU 实时（延迟 < 200ms / 1s 音频）

设计：
- SenseVoiceASR 类：单例懒加载模型
- transcribe(audio_bytes) -> str 接口
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import numpy as np


_MODEL_DIR = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "Shandianshuo", "models", "sensevoice-small"
)
_DEFAULT_MODEL_PATH = os.path.join(_MODEL_DIR, "model.onnx")
_DEFAULT_TOKENS_PATH = os.path.join(_MODEL_DIR, "tokens.json")

# 缓存 session（懒加载）
_session = None
_tokens: Optional[list] = None


def _get_session(model_path: str = _DEFAULT_MODEL_PATH):
    global _session
    if _session is None:
        import onnxruntime as ort
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"SenseVoice 模型未找到：{model_path}\n"
                f"请下载 SenseVoice-Small ONNX 到：{_MODEL_DIR}"
            )
        sess = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )
        _session = sess
    return _session


def _get_tokens(tokens_path: str = _DEFAULT_TOKENS_PATH) -> list:
    global _tokens
    if _tokens is None:
        with open(tokens_path, "r", encoding="utf-8") as f:
            _tokens = json.load(f)
    return _tokens


# ── 特征提取 ────────────────────────────────────────────────────
def _compute_fbank(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """提取 80 维 fbank 特征。"""
    import kaldi_native_fbank as knf
    opts = knf.FbankOptions()
    opts.mel_opts.num_bins = 80
    opts.frame_opts.samp_freq = float(sample_rate)
    opts.frame_opts.frame_length_ms = 25.0
    opts.frame_opts.frame_shift_ms = 10.0
    opts.frame_opts.window_type = "hamming"
    fbank = knf.OnlineFbank(opts)
    fbank.accept_waveform(sample_rate, audio.astype(np.float32).flatten())
    fbank.input_finished()
    n = fbank.num_frames_ready
    if n == 0:
        return np.zeros((0, 80), dtype=np.float32)
    feats = np.array([fbank.get_frame(i) for i in range(n)], dtype=np.float32)
    return feats


def _apply_lfr(features: np.ndarray, lfr_m: int = 7, lfr_n: int = 6) -> np.ndarray:
    """LFR (Low Frame Rate) 堆叠：lfr_m 帧拼成 1 帧，shift lfr_n。"""
    T, D = features.shape
    if T < lfr_m:
        # 不足时 pad 0
        pad = np.zeros((lfr_m - T, D), dtype=np.float32)
        features = np.concatenate([pad, features], axis=0)
        T = features.shape[0]
    num_out = (T - lfr_m) // lfr_n + 1
    out = np.zeros((num_out, lfr_m * D), dtype=np.float32)
    for i in range(num_out):
        out[i] = features[i * lfr_n : i * lfr_n + lfr_m].flatten()
    return out


# ── CTC 解码 ────────────────────────────────────────────────────
def _greedy_decode(logits: np.ndarray, tokens: list, blank_id: int = 0) -> str:
    """贪心 CTC 解码：argmax + 去重 + 去 blank + 去 special tokens。"""
    pred_ids = np.argmax(logits, axis=-1)
    result_ids: list[int] = []
    prev = -1
    for pid in pred_ids:
        pid = int(pid)
        if pid != prev and pid != blank_id:
            # 跳过 special tokens：<unk>=0, <s>=1, </s>=2, <|...|>=24884+
            if pid < 3 or pid >= 24884:
                pass  # 跳过
            else:
                result_ids.append(pid)
        prev = pid
    # tokens 是 list，idx → char
    chars: list[str] = []
    for tid in result_ids:
        if 0 <= tid < len(tokens):
            t = tokens[tid]
            # SentencePiece 用 ▁ (U+2581) 标记词首，替换为空格
            if t.startswith("▁"):
                t = " " + t[1:]
            chars.append(t)
    return "".join(chars).strip()


# SenseVoice 特殊 token id 范围
# 注：模型 embed 表只有 16 个 lang + 16 个 textnorm 槽位
# 实际可用的 id 范围是 [0..15]（通过负值索引也行）
# 14 = "auto" / 15 = withitn (经验值；不同模型导出可能不同)
_LANG_IDS = {
    "auto": 14,
    "zh": 0,
    "en": 1,
    "ja": 2,
    "ko": 3,
    "yue": 4,
}
_ITN_WITH = 15
_ITN_WITHOUT = 0


# ── 公开接口 ────────────────────────────────────────────────────
def transcribe(audio: np.ndarray, sample_rate: int = 16000,
               language: str = "zh", use_itn: bool = True) -> str:
    """把一段音频转成文字。

    Args:
        audio: float32 numpy 数组（单声道）
        sample_rate: 默认 16000
        language: 'zh' / 'en' / 'ja' / 'ko' / 'yue' / 'auto'
        use_itn: 是否做文本规范化

    Returns:
        识别出的文字
    """
    if audio.size == 0 or np.max(np.abs(audio)) < 0.001:
        return ""

    # 1. 特征
    feats = _compute_fbank(audio, sample_rate)
    if feats.shape[0] < 7:
        return ""
    lfr = _apply_lfr(feats)

    # 2. language id（默认 auto）
    lang_id = _LANG_IDS.get(language, _LANG_IDS["auto"])
    textnorm_id = _ITN_WITH if use_itn else _ITN_WITHOUT

    # 3. 推理
    sess = _get_session()
    speech = lfr[np.newaxis, :, :]  # (1, T, 560)
    speech_lengths = np.array([lfr.shape[0]], dtype=np.int32)
    language_in = np.array([lang_id], dtype=np.int32)
    textnorm_in = np.array([textnorm_id], dtype=np.int32)

    outputs = sess.run(
        None,
        {
            "speech": speech,
            "speech_lengths": speech_lengths,
            "language": language_in,
            "textnorm": textnorm_in,
        },
    )
    logits = outputs[0][0]  # (T', 25055)

    # 4. 解码
    tokens = _get_tokens()
    text = _greedy_decode(logits, tokens)
    return text.strip()


# ── 便捷函数 ────────────────────────────────────────────────────
def transcribe_wav_file(path: str, **kwargs) -> str:
    """从 WAV 文件转文字。"""
    import soundfile as sf
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return transcribe(audio, sr, **kwargs)


def is_model_available() -> bool:
    """检查本地模型是否就绪。"""
    return os.path.isfile(_DEFAULT_MODEL_PATH) and os.path.isfile(_DEFAULT_TOKENS_PATH)
