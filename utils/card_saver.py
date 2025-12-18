"""辅助保存生成的学生证 PNG。"""

from pathlib import Path
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


def maybe_save_student_card(img_data: bytes, verification_id: Optional[str], prefix: str) -> None:
    """在启用配置时，将学生证 PNG 保存到本地目录。

    Args:
        img_data: PNG 二进制数据。
        verification_id: 当前验证 ID（用于文件名，允许为 None）。
        prefix: 业务前缀，避免多服务命名冲突。
    """

    if not config.SAVE_STUDENT_CARD:
        return

    output_dir = Path(config.STUDENT_CARD_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{prefix}_{verification_id or 'card'}.png"
    file_path = output_dir / file_name

    try:
        file_path.write_bytes(img_data)
        logger.info("📁 学生证 PNG 已保存到 %s", file_path)
    except Exception as exc:  # pragma: no cover - 文件系统异常无需中断主流程
        logger.warning("⚠️ 保存学生证 PNG 失败：%s", exc)
