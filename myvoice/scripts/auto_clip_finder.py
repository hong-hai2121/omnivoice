#!/usr/bin/env python3
"""Đề xuất đoạn cắt video ngắn từ kịch bản truyện tiếng Việt.

Ví dụ:
    python auto_clip_finder.py kich_ban.txt
    python auto_clip_finder.py kich_ban.txt --top 10 --output-dir ket_qua
    python auto_clip_finder.py kich_ban.txt --long-from-start --target-minutes 12

Phiên bản này không gọi API hay dùng thư viện ngoài. Điểm số là heuristic dựa
trên từ khóa, lời thoại, mức độ căng thẳng và rủi ro lộ kết.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


# Các từ khóa có thể được điều chỉnh theo phong cách nội dung của từng kênh.
HOOK_KEYWORDS = (
    "không ngờ",
    "ai ngờ",
    "thực chất",
    "bí mật",
    "phát hiện",
    "hóa ra",
    "đột nhiên",
    "bất ngờ",
    "chưa biết rằng",
    "sắp",
    "nguy hiểm",
    "kỳ lạ",
    "không ổn",
)

CONFLICT_KEYWORDS = (
    "chỉ trích",
    "mắng",
    "vu khống",
    "oan",
    "ăn chặn",
    "cãi",
    "tranh cãi",
    "ném",
    "đẩy",
    "khinh",
    "chửi",
    "không tin",
    "đứng về phía",
    "bắt nạt",
)

CURIOSITY_KEYWORDS = (
    "vì sao",
    "tại sao",
    "rốt cuộc",
    "chuyện gì",
    "không ai biết",
    "liệu",
    "ẩn sau",
    "sự thật",
    "đằng sau",
    "bí mật",
    "lạ",
)

DANGER_KEYWORDS = (
    "màu xanh",
    "ôi thiu",
    "ngộ độc",
    "nôn",
    "tiêu chảy",
    "cấp cứu",
    "bệnh viện",
    "hôn mê",
    "độc",
    "chết",
    "thịt chết",
    "bẩn",
    "mùi lạ",
)

SPOILER_KEYWORDS = (
    "cuối cùng",
    "kết án",
    "tuyên án",
    "vào tù",
    "ra tòa",
    "bị xử",
    "không qua khỏi",
    "kết cục",
    "sự thật bại lộ",
    "mọi chuyện đã rõ",
)

SECRET_KEYWORDS = (
    "bí mật",
    "thực chất",
    "hóa ra",
    "chưa biết rằng",
    "không ai biết",
    "ẩn sau",
    "đằng sau",
)

WRONGED_KEYWORDS = (
    "vu khống",
    "oan",
    "hiểu lầm",
    "không tin",
    "chỉ trích",
    "bắt nạt",
)

DISCOVERY_KEYWORDS = (
    "phát hiện",
    "kỳ lạ",
    "không ổn",
    "mùi lạ",
    "hóa ra",
    "dấu hiệu",
    "bất thường",
)

ANTICIPATION_KEYWORDS = (
    "sắp",
    "chuẩn bị",
    "ngay lúc đó",
    "rồi sẽ",
    "không ngờ",
    "chưa biết rằng",
    "có lẽ",
)

EXPLANATION_KEYWORDS = (
    "bởi vì",
    "do đó",
    "vì thế",
    "để giải thích",
    "nguyên nhân là",
    "theo đó",
)


class ClipFinderError(Exception):
    """Lỗi có thể hiển thị trực tiếp cho người dùng CLI."""


@dataclass
class ClipCandidate:
    """Một đoạn 4–9 câu cùng kết quả chấm điểm của nó."""

    start_sentence: int
    end_sentence: int
    text: str
    score: int
    clip_type: str
    reason: str
    suggested_title: str
    suggested_hook: str
    features: dict[str, Any] = field(repr=False)

    def to_export_dict(self, clip_id: int) -> dict[str, Any]:
        """Trả về đúng cấu trúc công khai cho file JSON."""
        return {
            "clip_id": clip_id,
            "start_sentence": self.start_sentence,
            "end_sentence": self.end_sentence,
            "score": self.score,
            "clip_type": self.clip_type,
            "reason": self.reason,
            "suggested_title": self.suggested_title,
            "suggested_hook": self.suggested_hook,
            "text": self.text,
        }


def read_script(path: Path) -> str:
    """Đọc file text với các encoding thường gặp cho tiếng Việt."""
    if not path.exists():
        raise ClipFinderError(f"Không tìm thấy file kịch bản: {path}")
    if not path.is_file():
        raise ClipFinderError(f"Đường dẫn không phải là file: {path}")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ClipFinderError(f"Không thể đọc file '{path}': {exc}") from exc

    if not raw.strip():
        raise ClipFinderError("File kịch bản đang rỗng.")

    # UTF-8 là ưu tiên. cp1258 hỗ trợ nhiều file text tiếng Việt cũ trên Windows.
    for encoding in ("utf-8-sig", "utf-8", "cp1258"):
        try:
            content = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if content.strip():
            return content

    raise ClipFinderError(
        "Không đọc được mã hóa của file. Hãy lưu kịch bản ở UTF-8 rồi chạy lại."
    )


def split_sentences(text: str) -> list[str]:
    """Tách câu đủ ổn định cho văn bản tiếng Việt và giữ lại dấu câu.

    Xuống dòng không có dấu kết câu vẫn được coi là ranh giới câu để không làm
    mất các câu thoại/ngắt đoạn trong transcript.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # Đưa dấu đóng ngoặc kép/ngoặc sau dấu câu về cùng câu trước đó.
    normalized = re.sub(r'([.!?…]+)([”"’»)]*)[ \t]+', r"\1\2\n", normalized)

    pieces = re.split(r"(?<=[.!?…])[ \t]+|\n+", normalized)
    sentences: list[str] = []
    for piece in pieces:
        cleaned = re.sub(r"\s+", " ", piece).strip()
        if cleaned:
            sentences.append(cleaned)
    return sentences


def count_words(sentences: Iterable[str]) -> int:
    """Đếm từ theo khoảng trắng để ước lượng thời lượng đọc lời thoại."""
    return sum(len(sentence.split()) for sentence in sentences)


def count_keyword_hits(text: str, keywords: Iterable[str]) -> int:
    """Đếm cụm từ nguyên vẹn, không nhầm một phần của từ khác."""
    lowered = text.casefold()
    total = 0
    for keyword in keywords:
        pattern = rf"(?<!\w){re.escape(keyword.casefold())}(?!\w)"
        total += len(re.findall(pattern, lowered))
    return total


def has_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    return count_keyword_hits(text, keywords) > 0


def has_direct_dialogue(text: str) -> bool:
    """Nhận biết câu thoại trong dấu ngoặc kép hoặc bắt đầu bằng gạch đầu dòng."""
    return bool(re.search(r'["“”]|(?:^|\s)[—–-]\s+\S', text))


def sentence_position_bonus(start_sentence: int, total_sentences: int) -> tuple[int, str]:
    """Ưu tiên 20–70% đầu truyện; hạ điểm khi đi sâu vào đoạn kết."""
    position = (start_sentence - 1) / max(total_sentences - 1, 1)
    if 0.20 <= position <= 0.70:
        return 5, "nằm trong vùng 20–70% đầu truyện"
    if 0.10 <= position < 0.80:
        return 2, "nằm ngoài vùng ưu tiên nhưng chưa sát đoạn kết"
    if position > 0.85:
        return -15, "nằm rất gần cuối truyện"
    if position > 0.70:
        return -7, "nằm ở phần sau truyện"
    return 0, "nằm ở phần mở đầu"


def choose_clip_type(features: dict[str, Any]) -> str:
    """Chọn một nhãn chính, theo yếu tố hấp dẫn mạnh nhất của đoạn."""
    if features["wronged"]:
        return "Bị oan"
    if features["danger"]:
        return "Cảnh báo nguy hiểm"
    if features["secret"] or features["discovery"]:
        return "Phát hiện bí mật"
    if features["conflict"]:
        return "Mâu thuẫn"
    if features["opening_shock"]:
        return "Hook mở đầu"
    return "Cao trào nhẹ"


def title_and_hook(clip_type: str, first_sentence: str) -> tuple[str, str]:
    """Sinh tiêu đề/câu mở đầu an toàn, không cố tiết lộ kết truyện."""
    templates = {
        "Bị oan": (
            "Bị hiểu lầm trước mọi người, nhưng sự thật vẫn chưa được nói ra",
            "Họ đều tin nhân vật chính có lỗi, nhưng không ai biết điều gì đang bị che giấu...",
        ),
        "Cảnh báo nguy hiểm": (
            "Dấu hiệu nguy hiểm xuất hiện, nhưng không ai kịp nhận ra",
            "Không ai ngờ chi tiết bất thường này có thể dẫn đến chuyện lớn...",
        ),
        "Phát hiện bí mật": (
            "Một chi tiết bất thường đang hé lộ bí mật chưa ai biết",
            "Ngay khi phát hiện điều này, mọi thứ bỗng trở nên không ổn...",
        ),
        "Mâu thuẫn": (
            "Cuộc tranh cãi bùng nổ, nhưng chuyện đáng ngờ mới chỉ bắt đầu",
            "Chỉ một câu nói cũng đủ khiến mọi người quay sang đối đầu nhau...",
        ),
        "Hook mở đầu": (
            "Không ai ngờ câu chuyện lại rẽ sang hướng này",
            "Chuyện xảy ra tiếp theo khiến tất cả phải đặt câu hỏi...",
        ),
        "Cao trào nhẹ": (
            "Chuyện gì đang xảy ra phía sau tình huống này?",
            "Mọi thứ tưởng bình thường, cho đến khi một chi tiết khiến ai cũng nghi ngờ...",
        ),
    }
    title, hook = templates[clip_type]

    # Nếu câu mở có một chi tiết ngắn, thêm nó vào title để gợi đúng ngữ cảnh.
    seed = re.sub(r'^["“”\s—–-]+|[.!?…"“”]+$', "", first_sentence).strip()
    words = seed.split()
    if 5 <= len(words) <= 14 and not has_any_keyword(seed, SPOILER_KEYWORDS):
        title = f"{title}: {seed}"
    return title, hook


def build_reason(features: dict[str, Any], position_note: str) -> str:
    """Tạo lý do ngắn gọn, nhưng trả lời đủ sức hút, cliffhanger và spoiler."""
    reasons: list[str] = []
    if features["opening_shock"]:
        reasons.append("Câu mở có yếu tố bất ngờ hoặc gây sốc.")
    if features["wronged"]:
        reasons.append("Có tình huống bị oan, bị hiểu lầm hoặc bị công kích.")
    elif features["conflict"]:
        reasons.append("Có mâu thuẫn/cãi vã rõ ràng giữa các nhân vật.")
    if features["secret"]:
        reasons.append("Đoạn gợi ra bí mật hoặc thông tin chưa được tiết lộ.")
    if features["discovery"] and not features["secret"]:
        reasons.append("Nhân vật phát hiện một chi tiết bất thường.")
    if features["danger"]:
        reasons.append("Có dấu hiệu nguy hiểm hoặc rủi ro, tạo cảm giác khẩn cấp.")
    if features["dialogue"]:
        reasons.append("Có câu thoại trực tiếp, thuận lợi để dựng short có nhịp.")
    if features["anticipation"]:
        reasons.append("Không khí cho thấy một sự việc lớn có thể sắp xảy ra.")

    if features["cliffhanger"]:
        reasons.append("Câu kết tạo khoảng trống thông tin, phù hợp để kéo người xem về video gốc.")
    else:
        reasons.append("Đoạn dừng trước khi tình huống được giải quyết hoàn toàn.")

    if features["spoiler_hits"]:
        reasons.append("Có tín hiệu lộ kết nên điểm đã bị trừ; cần dựng thận trọng.")
    else:
        reasons.append("Không có từ khóa lộ kết rõ ràng.")

    reasons.append(f"Vị trí đoạn: {position_note}.")
    return " ".join(reasons)


def score_candidate(
    sentences: list[str], start_index: int, end_index: int, total_sentences: int
) -> ClipCandidate:
    """Chấm một đoạn ứng viên. start/end là index 0-based, end exclusive."""
    selected = sentences[start_index:end_index]
    text = " ".join(selected)
    opening = " ".join(selected[:2])
    ending = selected[-1]

    hook_hits = count_keyword_hits(text, HOOK_KEYWORDS)
    conflict_hits = count_keyword_hits(text, CONFLICT_KEYWORDS)
    curiosity_hits = count_keyword_hits(text, CURIOSITY_KEYWORDS)
    danger_hits = count_keyword_hits(text, DANGER_KEYWORDS)
    spoiler_hits = count_keyword_hits(text, SPOILER_KEYWORDS)

    opening_shock = has_any_keyword(opening, HOOK_KEYWORDS) or "!" in opening
    secret = has_any_keyword(text, SECRET_KEYWORDS)
    wronged = has_any_keyword(text, WRONGED_KEYWORDS)
    discovery = has_any_keyword(text, DISCOVERY_KEYWORDS)
    conflict = conflict_hits > 0
    danger = danger_hits > 0
    dialogue = has_direct_dialogue(text)
    anticipation = has_any_keyword(text, ANTICIPATION_KEYWORDS)
    has_question = "?" in text or has_any_keyword(text, CURIOSITY_KEYWORDS)
    ending_open = (
        "?" in ending
        or "..." in ending
        or "…" in ending
        or has_any_keyword(ending, CURIOSITY_KEYWORDS)
        or has_any_keyword(ending, ANTICIPATION_KEYWORDS)
    )
    cliffhanger = ending_open and not has_any_keyword(ending, SPOILER_KEYWORDS)

    features: dict[str, Any] = {
        "hook_hits": hook_hits,
        "conflict_hits": conflict_hits,
        "curiosity_hits": curiosity_hits,
        "danger_hits": danger_hits,
        "spoiler_hits": spoiler_hits,
        "opening_shock": opening_shock,
        "secret": secret,
        "wronged": wronged,
        "discovery": discovery,
        "conflict": conflict,
        "danger": danger,
        "dialogue": dialogue,
        "anticipation": anticipation,
        "has_question": has_question,
        "cliffhanger": cliffhanger,
    }

    # Điểm cơ bản thấp để vẫn có đề xuất với một truyện ít từ khóa.
    score = 2
    if opening_shock:
        score += 7
    if secret:
        score += 7
    if wronged:
        score += 8
    if conflict:
        score += min(7, 3 + 2 * (conflict_hits - 1))
    if discovery:
        score += 6
    if danger:
        score += min(9, 6 + danger_hits)
    if dialogue:
        score += 3
    if anticipation:
        score += 4
    if has_question:
        score += 4
    if cliffhanger:
        score += 7

    # Nhiều loại tín hiệu độc lập thường tốt hơn một từ khóa được lặp lại.
    active_signals = sum(
        bool(value)
        for value in (
            opening_shock,
            secret,
            wronged,
            conflict,
            discovery,
            danger,
            dialogue,
            anticipation,
            has_question,
        )
    )
    score += min(5, max(0, active_signals - 2))

    position_delta, position_note = sentence_position_bonus(start_index + 1, total_sentences)
    score += position_delta

    # Những từ này thường cho biết phần kết đã được kể ra.
    if spoiler_hits:
        score -= min(30, 12 * spoiler_hits)

    # Phạt đoạn dài, thiên về giải thích nhưng thiếu xung đột/câu hỏi/rủi ro.
    explanatory_hits = count_keyword_hits(text, EXPLANATION_KEYWORDS)
    no_tension = not any((conflict, secret, discovery, danger, has_question, dialogue))
    if len(text) > 650 and no_tension:
        score -= 6
    elif explanatory_hits >= 2 and no_tension:
        score -= 4

    clip_type = choose_clip_type(features)
    title, hook = title_and_hook(clip_type, selected[0])
    return ClipCandidate(
        start_sentence=start_index + 1,
        end_sentence=end_index,
        text=text,
        score=max(0, int(score)),
        clip_type=clip_type,
        reason=build_reason(features, position_note),
        suggested_title=title,
        suggested_hook=hook,
        features=features,
    )


def build_long_clip_from_start(
    sentences: list[str], target_minutes: float, words_per_minute: float
) -> ClipCandidate:
    """Tạo một clip dài duy nhất từ câu đầu, gần thời lượng mong muốn nhất.

    Không có timestamp thì thời lượng chỉ là ước lượng theo số từ. Hàm chỉ tìm
    điểm dừng ở ranh giới câu, trong một vùng nhỏ quanh số từ mục tiêu, rồi ưu
    tiên câu kết còn gợi tò mò thay vì câu có dấu hiệu lộ kết.
    """
    if len(sentences) < 4:
        raise ClipFinderError("Cần ít nhất 4 câu để tạo clip dài từ đầu truyện.")
    if target_minutes <= 0:
        raise ClipFinderError("--target-minutes phải lớn hơn 0.")
    if words_per_minute <= 0:
        raise ClipFinderError("--words-per-minute phải lớn hơn 0.")

    cumulative_words: list[int] = []
    running_total = 0
    for sentence in sentences:
        running_total += len(sentence.split())
        cumulative_words.append(running_total)

    total_words = cumulative_words[-1]
    target_words = round(target_minutes * words_per_minute)
    ideal_end = next(
        (index + 1 for index, words in enumerate(cumulative_words) if words >= target_words),
        len(sentences),
    )

    # Giữ lựa chọn sát thời lượng đích, nhưng cho phép ± khoảng 10% số câu để
    # kết ở một điểm kể chuyện tự nhiên hơn.
    search_radius = max(6, min(25, round(ideal_end * 0.10)))
    first_end = max(4, ideal_end - search_radius)
    last_end = min(len(sentences), ideal_end + search_radius)

    def endpoint_value(end_sentence: int) -> tuple[float, int]:
        window_start = max(0, end_sentence - 9)
        ending_window = score_candidate(
            sentences, window_start, end_sentence, len(sentences)
        )
        boundary_bonus = 0
        if ending_window.features["cliffhanger"]:
            boundary_bonus += 8
        if ending_window.features["anticipation"]:
            boundary_bonus += 3
        if ending_window.features["has_question"]:
            boundary_bonus += 3
        if ending_window.features["spoiler_hits"]:
            boundary_bonus -= 12
        distance = abs(cumulative_words[end_sentence - 1] - target_words)
        # Thời lượng vẫn là yếu tố chính; bonus chỉ dùng để chọn giữa các mốc gần nhau.
        return boundary_bonus * 25 - distance, -distance

    end_sentence = max(range(first_end, last_end + 1), key=endpoint_value)
    opening_window = score_candidate(sentences, 0, min(9, len(sentences)), len(sentences))
    ending_window = score_candidate(
        sentences, max(0, end_sentence - 9), end_sentence, len(sentences)
    )
    selected_words = cumulative_words[end_sentence - 1]
    estimated_minutes = selected_words / words_per_minute
    story_percentage = selected_words / total_words * 100

    if ending_window.features["cliffhanger"]:
        ending_reason = "Điểm dừng có câu hỏi/tín hiệu chưa giải quyết, nên vẫn tạo tò mò."
    elif ending_window.features["spoiler_hits"]:
        ending_reason = "Điểm dừng có ít nhiều dấu hiệu lộ kết; nên xem lại khi dựng."
    else:
        ending_reason = "Điểm dừng ở cuối câu và chưa có từ khóa lộ kết rõ ràng."

    reason = (
        f"Đây là clip dài duy nhất, đi từ câu 1 đến câu {end_sentence}. "
        f"Ước tính {estimated_minutes:.1f} phút ở tốc độ {words_per_minute:g} từ/phút "
        f"({selected_words:,} từ, khoảng {story_percentage:.0f}% kịch bản). "
        f"Phần mở có dạng {opening_window.clip_type.lower()}, tạo lý do giữ người xem. "
        f"{ending_reason}"
    )
    return ClipCandidate(
        start_sentence=1,
        end_sentence=end_sentence,
        text=" ".join(sentences[:end_sentence]),
        score=opening_window.score,
        clip_type=opening_window.clip_type,
        reason=reason,
        suggested_title=opening_window.suggested_title,
        suggested_hook=opening_window.suggested_hook,
        features=opening_window.features,
    )


def _require_media_binary(binary_name: str) -> str:
    """Trả về đường dẫn executable FFmpeg/FFprobe hoặc báo lỗi rõ ràng."""
    executable = shutil.which(binary_name)
    if not executable:
        raise ClipFinderError(
            f"Không tìm thấy {binary_name}. Hãy cài FFmpeg và thêm nó vào PATH."
        )
    return executable


def probe_audio_duration(audio_path: Path) -> float:
    """Đọc chính xác thời lượng audio qua FFprobe."""
    if not audio_path.exists() or not audio_path.is_file():
        raise ClipFinderError(f"Không tìm thấy file audio: {audio_path}")

    result = subprocess.run(
        [
            _require_media_binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise ClipFinderError(f"FFprobe không đọc được audio: {result.stderr.strip()}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise ClipFinderError("FFprobe không trả về thời lượng audio hợp lệ.") from exc
    if duration <= 0:
        raise ClipFinderError("Audio có thời lượng không hợp lệ.")
    return duration


def find_sentence_end_silence(
    audio_path: Path,
    target_minutes: float,
    min_minutes: float,
    max_minutes: float,
    silence_db: float,
    min_silence: float,
) -> tuple[float, float]:
    """Tìm đầu khoảng lặng gần mốc cần cắt nhất.

    TTS thường chèn khoảng lặng sau mỗi câu. Cắt tại *đầu* khoảng lặng nghĩa
    là từ cuối cùng đã đọc xong, không lấy phần đầu của câu kế tiếp. Chỉ các
    khoảng lặng dài tối thiểu ``min_silence`` mới được xem là ranh giới câu.
    """
    if not 0 < min_minutes <= max_minutes:
        raise ClipFinderError("Khoảng thời lượng phải thỏa 0 < min <= max.")
    if min_silence <= 0:
        raise ClipFinderError("--min-silence phải lớn hơn 0.")

    duration = probe_audio_duration(audio_path)
    lower_bound = min_minutes * 60
    upper_bound = min(max_minutes * 60, duration)
    if lower_bound >= duration:
        raise ClipFinderError(
            "Audio ngắn hơn thời lượng tối thiểu yêu cầu; không thể cắt clip 10–15 phút."
        )

    # Chỉ phân tích khu vực 10–15 phút nên việc dò rất nhanh, kể cả audio dài.
    scan_start = max(0.0, lower_bound - 3.0)
    scan_duration = min(duration - scan_start, upper_bound - scan_start + 3.0)
    ffmpeg = _require_media_binary("ffmpeg")
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-ss",
            f"{scan_start:.6f}",
            "-t",
            f"{scan_duration:.6f}",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=n={silence_db}dB:d={min_silence}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise ClipFinderError(f"FFmpeg không dò được khoảng lặng: {result.stderr.strip()}")

    pending_start: float | None = None
    silences: list[tuple[float, float]] = []
    start_pattern = re.compile(r"silence_start:\s*([0-9.]+)")
    end_pattern = re.compile(
        r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)"
    )
    for line in result.stderr.splitlines():
        start_match = start_pattern.search(line)
        if start_match:
            pending_start = float(start_match.group(1))
            continue
        end_match = end_pattern.search(line)
        if end_match and pending_start is not None:
            end = float(end_match.group(1))
            detected_duration = float(end_match.group(2))
            if detected_duration >= min_silence:
                silence_start = scan_start + pending_start
                silence_end = scan_start + end
                if lower_bound <= silence_start <= upper_bound:
                    silences.append((silence_start, silence_end))
            pending_start = None

    if not silences:
        raise ClipFinderError(
            "Không tìm thấy khoảng lặng đủ dài trong vùng cần cắt. "
            "Thử giảm --min-silence, ví dụ 0.25."
        )

    target_seconds = min(max(target_minutes * 60, lower_bound), upper_bound)
    # Ưu tiên mốc gần thời lượng đích nhất; nếu bằng nhau, ưu tiên khoảng lặng dài hơn.
    cut_start, _cut_end = min(
        silences,
        key=lambda item: (abs(item[0] - target_seconds), -(item[1] - item[0])),
    )
    return cut_start, duration


def estimate_sentence_at_audio_time(
    sentences: list[str], audio_duration: float, cut_seconds: float
) -> int:
    """Ước lượng câu tương ứng để báo cáo; không dùng nó làm điểm cắt audio."""
    total_words = count_words(sentences)
    target_words = total_words * cut_seconds / audio_duration
    running_total = 0
    for index, sentence in enumerate(sentences, start=1):
        running_total += len(sentence.split())
        if running_total >= target_words:
            return index
    return len(sentences)


def cut_audio_at_sentence_end(
    audio_path: Path,
    output_path: Path,
    target_minutes: float,
    min_minutes: float,
    max_minutes: float,
    silence_db: float,
    min_silence: float,
) -> tuple[float, float]:
    """Cắt audio từ đầu đến một khoảng lặng sau câu; không tạo JSON/TXT."""
    cut_seconds, source_duration = find_sentence_end_silence(
        audio_path,
        target_minutes,
        min_minutes,
        max_minutes,
        silence_db,
        min_silence,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ClipFinderError(f"Không thể tạo thư mục output audio: {exc}") from exc

    result = subprocess.run(
        [
            _require_media_binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(audio_path),
            "-t",
            f"{cut_seconds:.6f}",
            "-map",
            "0:a:0",
            "-c:a",
            "copy",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise ClipFinderError(f"FFmpeg không thể cắt audio: {result.stderr.strip()}")
    return cut_seconds, source_duration


def generate_candidates(
    sentences: list[str], min_sentences: int = 4, max_sentences: int = 9
) -> list[ClipCandidate]:
    """Tạo các cửa sổ trượt 4–9 câu để không bỏ sót điểm bắt đầu tốt."""
    total = len(sentences)
    if total < min_sentences:
        raise ClipFinderError(
            f"Kịch bản chỉ có {total} câu; cần ít nhất {min_sentences} câu để tạo một clip."
        )

    # Với truyện rất dài, giảm nhẹ mật độ cửa sổ để thời gian chạy vẫn hợp lý.
    stride = 1 if total <= 1_500 else 2 if total <= 5_000 else 3
    candidates: list[ClipCandidate] = []
    for size in range(min_sentences, min(max_sentences, total) + 1):
        last_start = total - size
        starts = list(range(0, last_start + 1, stride))
        if starts[-1] != last_start:
            starts.append(last_start)
        for start in starts:
            candidates.append(score_candidate(sentences, start, start + size, total))
    return candidates


def overlap_ratio(first: ClipCandidate, second: ClipCandidate) -> float:
    """Tỷ lệ phần giao trên đoạn ngắn hơn; 1.0 nghĩa là gần như trùng hoàn toàn."""
    overlap_start = max(first.start_sentence, second.start_sentence)
    overlap_end = min(first.end_sentence, second.end_sentence)
    overlap = max(0, overlap_end - overlap_start + 1)
    first_length = first.end_sentence - first.start_sentence + 1
    second_length = second.end_sentence - second.start_sentence + 1
    return overlap / min(first_length, second_length)


def select_best_clips(candidates: list[ClipCandidate], top: int) -> list[ClipCandidate]:
    """Chọn điểm cao nhất, đồng thời loại các cửa sổ trùng nhau quá nhiều."""
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.score,
            item.features["cliffhanger"],
            -item.features["spoiler_hits"],
            -(item.end_sentence - item.start_sentence),
        ),
        reverse=True,
    )

    selected: list[ClipCandidate] = []
    for candidate in ordered:
        if all(overlap_ratio(candidate, kept) < 0.55 for kept in selected):
            selected.append(candidate)
        if len(selected) == top:
            break

    # Với kịch bản ngắn, nới rất nhẹ ngưỡng để có đủ đề xuất nếu vẫn khác ít nhất 30%.
    if len(selected) < top:
        for candidate in ordered:
            if candidate in selected:
                continue
            if all(overlap_ratio(candidate, kept) < 0.70 for kept in selected):
                selected.append(candidate)
            if len(selected) == top:
                break

    return selected


def render_txt(suggestions: list[dict[str, Any]]) -> str:
    """Trình bày bản TXT dễ đọc cho khâu biên tập."""
    blocks: list[str] = ["GỢI Ý CẮT VIDEO NGẮN", "=" * 28]
    for clip in suggestions:
        blocks.extend(
            (
                "",
                f"CLIP #{clip['clip_id']} | Điểm: {clip['score']}",
                f"Phạm vi câu: {clip['start_sentence']}–{clip['end_sentence']}",
                f"Loại clip: {clip['clip_type']}",
                f"Lý do nên cắt: {clip['reason']}",
                f"Gợi ý tiêu đề: {clip['suggested_title']}",
                f"Gợi ý câu mở đầu: {clip['suggested_hook']}",
                "Nội dung đoạn được chọn:",
                clip["text"],
                "-" * 60,
            )
        )
    return "\n".join(blocks) + "\n"


def write_outputs(suggestions: list[ClipCandidate], output_dir: Path) -> tuple[Path, Path]:
    """Ghi hai file đầu ra với UTF-8, tạo thư mục đích nếu cần."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        exported = [clip.to_export_dict(index) for index, clip in enumerate(suggestions, start=1)]
        json_path = output_dir / "clip_suggestions.json"
        txt_path = output_dir / "clip_suggestions.txt"
        json_path.write_text(
            json.dumps(exported, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        txt_path.write_text(render_txt(exported), encoding="utf-8")
    except OSError as exc:
        raise ClipFinderError(f"Không thể ghi file kết quả: {exc}") from exc
    return json_path, txt_path


# --- Điểm mở rộng cho bản sau -------------------------------------------------
def load_timestamped_transcript(path: Path) -> list[dict[str, Any]]:
    """Nơi nối transcript Whisper sau này.

    Dự kiến mỗi phần tử có dạng:
    {"text": "...", "start": 12.4, "end": 16.8}.
    Sau đó có thể ánh xạ start_sentence/end_sentence sang mốc thời gian video.
    """
    raise NotImplementedError("Bản đầu chỉ nhận file kịch bản .txt không có timestamp.")


def build_ffmpeg_cut_command(input_video: Path, start_seconds: float, end_seconds: float) -> list[str]:
    """Trả về lệnh FFmpeg tham khảo, chưa tự chạy FFmpeg trong bản đầu."""
    return [
        "ffmpeg",
        "-ss",
        str(start_seconds),
        "-to",
        str(end_seconds),
        "-i",
        str(input_video),
        "-c",
        "copy",
        "output_clip.mp4",
    ]


def enrich_with_llm(candidate: ClipCandidate) -> ClipCandidate:
    """Điểm móc để bổ sung đánh giá bằng OpenAI API trong tương lai.

    Hàm giữ nguyên candidate để interface không làm hỏng luồng xử lý hiện tại.
    """
    return candidate


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phân tích kịch bản .txt và đề xuất đoạn cắt video ngắn.",
    )
    parser.add_argument("script", type=Path, help="Đường dẫn file kịch bản .txt")
    parser.add_argument(
        "--top",
        type=int,
        default=8,
        help="Số đề xuất cần xuất, từ 1 đến 10 (mặc định: 8)",
    )
    parser.add_argument(
        "--long-from-start",
        action="store_true",
        help=(
            "Xuất đúng một clip dài từ đầu truyện; dùng khi muốn lấy phần mở đầu "
            "10–15 phút thay vì teaser 4–9 câu."
        ),
    )
    parser.add_argument(
        "--target-minutes",
        type=float,
        default=12.0,
        help="Thời lượng đọc ước tính cho --long-from-start (mặc định: 12)",
    )
    parser.add_argument(
        "--words-per-minute",
        type=float,
        default=145.0,
        help="Tốc độ đọc dùng để ước lượng thời lượng (mặc định: 145)",
    )
    parser.add_argument(
        "--audio",
        type=Path,
        help="Audio nguồn để cắt thật tại khoảng lặng cuối câu (WAV/MP3/M4A/...)",
    )
    parser.add_argument(
        "--output-audio",
        type=Path,
        help="Audio đầu ra. Khi dùng cùng --audio, tool chỉ tạo audio, không tạo JSON/TXT.",
    )
    parser.add_argument(
        "--min-minutes",
        type=float,
        default=10.0,
        help="Thời lượng tối thiểu khi cắt audio (mặc định: 10)",
    )
    parser.add_argument(
        "--max-minutes",
        type=float,
        default=15.0,
        help="Thời lượng tối đa khi cắt audio (mặc định: 15)",
    )
    parser.add_argument(
        "--silence-db",
        type=float,
        default=-35.0,
        help="Ngưỡng im lặng dB của FFmpeg (mặc định: -35)",
    )
    parser.add_argument(
        "--min-silence",
        type=float,
        default=0.50,
        help="Khoảng lặng tối thiểu, tính bằng giây, để coi là hết câu (mặc định: 0.50)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Thư mục ghi clip_suggestions.json và clip_suggestions.txt (mặc định: thư mục hiện tại)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.top <= 10:
        parser.error("--top phải nằm trong khoảng từ 1 đến 10.")
    if args.target_minutes <= 0:
        parser.error("--target-minutes phải lớn hơn 0.")
    if args.words_per_minute <= 0:
        parser.error("--words-per-minute phải lớn hơn 0.")
    if not 0 < args.min_minutes <= args.max_minutes:
        parser.error("Cần thỏa 0 < --min-minutes <= --max-minutes.")
    if args.min_silence <= 0:
        parser.error("--min-silence phải lớn hơn 0.")
    if bool(args.audio) != bool(args.output_audio):
        parser.error("--audio và --output-audio phải được dùng cùng nhau.")
    return args


def configure_console_encoding() -> None:
    """Không để thông báo tiếng Việt làm CLI lỗi ở console Windows mã hóa cũ."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    args = parse_args(argv)
    try:
        script = read_script(args.script)
        sentences = split_sentences(script)
        if args.audio:
            cut_seconds, audio_duration = cut_audio_at_sentence_end(
                args.audio,
                args.output_audio,
                args.target_minutes,
                args.min_minutes,
                args.max_minutes,
                args.silence_db,
                args.min_silence,
            )
            sentence_number = estimate_sentence_at_audio_time(
                sentences, audio_duration, cut_seconds
            )
        elif args.long_from_start:
            candidates: list[ClipCandidate] = []
            selected = [
                build_long_clip_from_start(
                    sentences, args.target_minutes, args.words_per_minute
                )
            ]
        else:
            candidates = generate_candidates(sentences)
            selected = select_best_clips(candidates, args.top)
        if not args.audio:
            json_path, txt_path = write_outputs(selected, args.output_dir)
    except ClipFinderError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2

    if args.audio:
        minutes, seconds = divmod(cut_seconds, 60)
        print(
            f"Đã cắt audio tại {int(minutes)}:{seconds:05.2f}, ngay đầu khoảng lặng sau câu."
        )
        print(f"Mốc nội dung ước tính: hết câu {sentence_number}/{len(sentences)}.")
        print(f"Audio: {args.output_audio}")
    elif args.long_from_start:
        print(f"Đã tách {len(sentences)} câu và tạo một clip dài từ đầu truyện.")
    else:
        print(f"Đã tách {len(sentences)} câu và đánh giá {len(candidates)} đoạn ứng viên.")
    if not args.audio:
        print(f"Đã chọn {len(selected)} đoạn.")
        print(f"JSON: {json_path}")
        print(f"TXT : {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
