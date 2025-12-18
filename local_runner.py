"""在本地直接运行 SheerID 验证流程的 CLI。

该脚本绕过 Telegram 机器人，通过命令行直接触发各项认证，适合自用或调试。

示例：
    python local_runner.py --service spotify --url "https://services.sheerid.com/verify/..."
    python local_runner.py --service bolt --url "https://services.sheerid.com/..." --poll-code
"""
import argparse
import asyncio
import logging
from typing import Callable, Dict, Optional

import httpx

from one.sheerid_verifier import SheerIDVerifier as OneVerifier
from k12.sheerid_verifier import SheerIDVerifier as K12Verifier
from spotify.sheerid_verifier import SheerIDVerifier as SpotifyVerifier
from youtube.sheerid_verifier import SheerIDVerifier as YouTubeVerifier
from Boltnew.sheerid_verifier import SheerIDVerifier as BoltnewVerifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


class VerificationService:
    """描述单个验证服务的元数据和执行器。"""

    def __init__(
        self,
        name: str,
        verifier_cls,
        parser: Callable[[str], Optional[str]],
        description: str,
    ):
        self.name = name
        self.verifier_cls = verifier_cls
        self.parser = parser
        self.description = description

    def run(self, url: str) -> Dict:
        verification_id = self.parser(url)
        if not verification_id:
            raise ValueError("无法从链接中解析 verificationId，请检查 URL 是否正确")

        verifier = self.verifier_cls(verification_id)  # type: ignore[arg-type]
        return verifier.verify()


SERVICES: Dict[str, VerificationService] = {
    "gemini": VerificationService(
        "Gemini One Pro", OneVerifier, OneVerifier.parse_verification_id, "Gemini One Pro 教师认证",
    ),
    "k12": VerificationService(
        "ChatGPT Teacher K12", K12Verifier, K12Verifier.parse_verification_id, "ChatGPT Teacher K12 教师认证",
    ),
    "spotify": VerificationService(
        "Spotify Student", SpotifyVerifier, SpotifyVerifier.parse_verification_id, "Spotify 学生认证",
    ),
    "youtube": VerificationService(
        "YouTube Student Premium", YouTubeVerifier, YouTubeVerifier.parse_verification_id, "YouTube Premium 学生认证",
    ),
}


def _display_result(result: Dict) -> None:
    success = result.get("success")
    print("\n=== 验证结果 ===")
    print(f"状态      : {'成功' if success else '失败'}")

    if result.get("pending"):
        print("审核状态  : 已提交，等待人工审核")

    if result.get("redirect_url"):
        print(f"跳转链接  : {result['redirect_url']}")

    if message := result.get("message"):
        print(f"提示信息  : {message}")

    if not success:
        return

    if reward_code := result.get("reward_code"):
        print(f"奖励码    : {reward_code}")

    verification_id = result.get("verification_id")
    if verification_id:
        print(f"验证 ID  : {verification_id}")


async def _poll_bolt_reward_code(verification_id: str, max_wait: int, interval: int) -> Optional[str]:
    """轮询 Bolt.new 的 reward code，逻辑与机器人一致但用于本地 CLI。"""
    start = asyncio.get_event_loop().time()
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= max_wait:
                return None

            try:
                resp = await client.get(
                    f"https://my.sheerid.com/rest/v2/verification/{verification_id}"
                )
                data = resp.json()
                step = data.get("currentStep")

                if step == "success":
                    reward_code = data.get("rewardCode") or data.get("rewardData", {}).get("rewardCode")
                    if reward_code:
                        return reward_code
                elif step == "error":
                    return None
            except Exception as exc:  # pragma: no cover - 网络错误时继续重试
                logger.info(f"查询 reward code 出错：{exc}")

            await asyncio.sleep(interval)


async def run_bolt(url: str, poll_code: bool, max_wait: int, interval: int) -> None:
    verifier = BoltnewVerifier(url, verification_id=BoltnewVerifier.parse_verification_id(url))
    result = verifier.verify()

    if not result.get("success"):
        _display_result(result)
        return

    verification_id = result.get("verification_id") or verifier.verification_id
    result["verification_id"] = verification_id

    if poll_code and verification_id:
        print("正在轮询获取 Bolt.new 奖励码...")
        reward_code = await _poll_bolt_reward_code(verification_id, max_wait, interval)
        if reward_code:
            result["reward_code"] = reward_code
        else:
            print("在设定时间内未获取到奖励码，请稍后使用 verificationId 手动查询。")

    _display_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="在本地执行 SheerID 验证流程")
    parser.add_argument(
        "--service",
        choices=[*SERVICES.keys(), "bolt"],
        required=True,
        help="要运行的认证服务标识",
    )
    parser.add_argument("--url", required=True, help="完整的 SheerID 验证链接")
    parser.add_argument(
        "--poll-code",
        action="store_true",
        help="用于 Bolt.new：验证后额外轮询 reward code（默认等待 20 秒）",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=20,
        help="轮询奖励码的最大等待时间（秒，默认 20）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="轮询奖励码的间隔（秒，默认 5）",
    )
    args = parser.parse_args()

    if args.service == "bolt":
        asyncio.run(run_bolt(args.url, args.poll_code, args.wait, args.interval))
        return

    service = SERVICES[args.service]
    try:
        result = service.run(args.url)
    except ValueError as exc:
        logger.error(exc)
        return
    except Exception as exc:  # pragma: no cover - CLI 直接打印错误
        logger.error("验证失败：%s", exc)
        return

    _display_result(result)


if __name__ == "__main__":
    main()
