# -*- coding: utf-8 -*-
"""Đổi tên ảnh mới trong myvoice/Anh theo thứ tự số, trừ Pink.png.

Chạy trực tiếp script sẽ đổi tên. Dùng --dry-run nếu chỉ muốn xem trước.

Ví dụ chạy từ thư mục gốc OmniVoice:
    venv\Scripts\python myvoice\scripts\rename_images.py            # đổi tên thật
    venv\Scripts\python myvoice\scripts\rename_images.py --dry-run  # chỉ xem trước

Ảnh đã có tên số chuẩn như 1.png, 2.jpg, ... được giữ nguyên. Chỉ ảnh có tên
khác mới nhận số tiếp theo sau số lớn nhất đang có. Phần mở rộng được giữ nguyên.
Thứ tự ảnh mới được xác định theo tên hiện tại bằng natural sort (2 đứng trước 10).
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path


# Cho phép thông báo tiếng Việt khi chạy trực tiếp trên Windows/PowerShell.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE_DIR = BASE_DIR / "Anh"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EXCLUDED_NAMES = {"pink.png"}
NUMBERED_STEM = re.compile(r"[1-9]\d*$")


def natural_sort_key(path: Path) -> list[object]:
    """Sắp tên theo cách con người thường đọc: 2.png trước 10.png."""
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", path.name)]


def is_already_numbered(path: Path) -> bool:
    """True với tên số chuẩn: 1.png, 2.jpg, ...; không nhận 0.png hay 001.png."""
    return bool(NUMBERED_STEM.fullmatch(path.stem))


def collect_images(image_dir: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Trả về (ảnh mới cần đổi tên, ảnh đã đúng tên số, ảnh ngoại lệ)."""
    candidates = [
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
    ]
    excluded = sorted(
        (path for path in candidates if path.name.casefold() in EXCLUDED_NAMES),
        key=natural_sort_key,
    )
    numbered = sorted(
        (
            path
            for path in candidates
            if path.name.casefold() not in EXCLUDED_NAMES and is_already_numbered(path)
        ),
        key=natural_sort_key,
    )
    new_images = sorted(
        (
            path
            for path in candidates
            if path.name.casefold() not in EXCLUDED_NAMES and not is_already_numbered(path)
        ),
        key=natural_sort_key,
    )
    return new_images, numbered, excluded


def build_plan(images: list[Path], start: int) -> list[tuple[Path, Path]]:
    """Tạo danh sách đổi tên, giữ nguyên đuôi file của từng ảnh."""
    return [
        (source, source.with_name(f"{number}{source.suffix}"))
        for number, source in enumerate(images, start=start)
    ]


def validate_plan(plan: list[tuple[Path, Path]]) -> None:
    """Chặn đích trùng nhau hoặc đè lên file không nằm trong kế hoạch."""
    destination_names = [destination.name.casefold() for _, destination in plan]
    if len(destination_names) != len(set(destination_names)):
        raise ValueError("Tên đích bị trùng nhau; không thực hiện đổi tên.")

    source_names = {source.name.casefold() for source, _ in plan}
    blockers = [
        destination
        for _, destination in plan
        if destination.exists() and destination.name.casefold() not in source_names
    ]
    if blockers:
        details = "\n".join(f"  - {path.name}" for path in blockers)
        raise ValueError(
            "Các tên đích sau đã tồn tại nhưng không phải ảnh trong danh sách đổi tên:\n"
            f"{details}"
        )


def apply_plan(plan: list[tuple[Path, Path]]) -> None:
    """Đổi tên qua tên tạm để không va chạm với các tên số đang tồn tại."""
    staged: list[tuple[Path, Path, Path]] = []

    # Giai đoạn 1: giải phóng toàn bộ tên cũ.
    for index, (source, destination) in enumerate(plan, start=1):
        temporary = source.with_name(
            f".__rename_images_{uuid.uuid4().hex}_{index}{source.suffix}"
        )
        source.rename(temporary)
        staged.append((source, temporary, destination))

    # Giai đoạn 2: gán các tên số chính thức.
    try:
        for _, temporary, destination in staged:
            temporary.rename(destination)
    except OSError as exc:
        raise RuntimeError(
            "Không thể hoàn tất đổi tên. Một số file có thể đang mang tên tạm "
            "bắt đầu bằng .__rename_images_."
        ) from exc


def print_plan(
    plan: list[tuple[Path, Path]],
    numbered: list[Path],
    excluded: list[Path],
    dry_run: bool,
) -> None:
    if numbered:
        print(f"Giữ nguyên {len(numbered)} ảnh đã có tên số chuẩn.")

    if excluded:
        print("Ngoại lệ, giữ nguyên:")
        for path in excluded:
            print(f"  - {path.name}")

    print(f"\n{len(plan)} ảnh mới sẽ được đổi tên:")
    for source, destination in plan:
        marker = "=" if source.name == destination.name else "→"
        print(f"  {source.name} {marker} {destination.name}")

    if dry_run:
        print("\nĐây là chế độ xem trước; chưa có file nào được đổi tên.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Đổi tên ảnh trong myvoice/Anh theo thứ tự số, bỏ qua Pink.png."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_IMAGE_DIR,
        help=f"Thư mục ảnh (mặc định: {DEFAULT_IMAGE_DIR})",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Số nhỏ nhất có thể dùng cho ảnh mới (mặc định: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ xem danh sách đổi tên, không sửa file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_dir = args.dir.expanduser().resolve()

    if args.start < 0:
        print("--start phải lớn hơn hoặc bằng 0.", file=sys.stderr)
        return 2
    if not image_dir.is_dir():
        print(f"Không tìm thấy thư mục ảnh: {image_dir}", file=sys.stderr)
        return 2

    images, numbered, excluded = collect_images(image_dir)
    if not images:
        print(f"Không có ảnh mới cần đổi tên trong: {image_dir}")
        return 0

    next_number = max((int(path.stem) for path in numbered), default=0) + 1
    plan = build_plan(images, max(args.start, next_number))
    try:
        validate_plan(plan)
    except ValueError as exc:
        print(f"Dừng: {exc}", file=sys.stderr)
        return 2

    print_plan(plan, numbered, excluded, args.dry_run)
    if args.dry_run:
        return 0

    try:
        apply_plan(plan)
    except (OSError, RuntimeError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    print("\nĐã đổi tên xong.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
