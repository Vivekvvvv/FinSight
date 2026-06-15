#!/usr/bin/env python3
"""
自动抓取国务院办公厅次年节假日安排并更新 cn_holiday.py

数据来源：
- 国务院官网：http://www.gov.cn/zhengce/content/
- 搜索关键词："国务院办公厅关于{year}年部分节假日安排的通知"

更新策略：
1. 抓取次年节假日通知
2. 解析节假日日期（元旦、春节、清明、劳动节、端午、中秋、国庆）
3. 识别调休工作日（周末改为工作日）
4. 更新 backend/services/cn_holiday.py
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# 节假日名称映射
HOLIDAY_NAMES = {
    "元旦": "元旦",
    "春节": "春节",
    "清明": "清明节",
    "劳动": "劳动节",
    "五一": "劳动节",
    "端午": "端午节",
    "中秋": "中秋节",
    "国庆": "国庆节",
}


def fetch_holiday_notice(year: int) -> str | None:
    """
    抓取国务院办公厅节假日安排通知

    Args:
        year: 目标年份

    Returns:
        通知全文，失败返回None
    """
    # 搜索国务院官网
    search_url = "http://sousuo.gov.cn/s.htm"
    params = {
        "t": "zhengce",
        "q": f"国务院办公厅关于{year}年部分节假日安排的通知",
        "timetype": "timeqb",
        "mintime": f"{year-1}-01-01",
        "maxtime": f"{year}-12-31",
        "sort": "relevance",
    }

    try:
        resp = requests.get(search_url, params=params, timeout=10)
        resp.raise_for_status()

        # 解析搜索结果，获取第一条链接
        soup = BeautifulSoup(resp.text, "html.parser")
        first_result = soup.select_one(".res-list h3 a")

        if not first_result or not first_result.get("href"):
            print(f"未找到{year}年节假日通知", file=sys.stderr)
            return None

        notice_url = first_result["href"]
        print(f"找到通知页面: {notice_url}")

        # 获取通知正文
        notice_resp = requests.get(notice_url, timeout=10)
        notice_resp.raise_for_status()

        notice_soup = BeautifulSoup(notice_resp.text, "html.parser")
        content = notice_soup.select_one(".pages_content, .article")

        if not content:
            print("无法解析通知正文", file=sys.stderr)
            return None

        return content.get_text()

    except Exception as e:
        print(f"抓取失败: {e}", file=sys.stderr)
        return None


def parse_holidays(text: str, year: int) -> dict[date, str]:
    """
    解析节假日文本，提取日期

    Args:
        text: 通知正文
        year: 目标年份

    Returns:
        {date(2026, 1, 1): "元旦", ...}
    """
    holidays = {}

    # 正则提取日期范围："1月1日至3日"、"2月10日至17日"
    pattern = r"(\d{1,2})月(\d{1,2})日(?:至(\d{1,2})日)?"

    for match in re.finditer(pattern, text):
        month = int(match.group(1))
        start_day = int(match.group(2))
        end_day = int(match.group(3)) if match.group(3) else start_day

        # 识别节假日名称（向前查找）
        context = text[max(0, match.start() - 50) : match.start()]
        holiday_name = "未知"
        for keyword, name in HOLIDAY_NAMES.items():
            if keyword in context:
                holiday_name = name
                break

        # 生成日期范围
        for day in range(start_day, end_day + 1):
            try:
                d = date(year, month, day)
                holidays[d] = holiday_name
            except ValueError:
                pass  # 无效日期

    return holidays


def parse_workday_overrides(text: str, year: int) -> dict[date, str]:
    """
    解析调休工作日（周末改为上班）

    示例文本："2月7日（星期六）、2月28日（星期六）上班"

    Args:
        text: 通知正文
        year: 目标年份

    Returns:
        {date(2026, 2, 7): "春节前调休", ...}
    """
    workdays = {}

    # 正则：提取"X月X日（星期X）上班"
    pattern = r"(\d{1,2})月(\d{1,2})日（星期[一二三四五六日]）[、，]?(?=.*?上班)"

    for match in re.finditer(pattern, text):
        month = int(match.group(1))
        day = int(match.group(2))

        try:
            d = date(year, month, day)

            # 识别调休原因（春节前/国庆后等）
            context = text[max(0, match.start() - 100) : match.start()]
            reason = "调休"
            if "春节" in context:
                reason = "春节前调休" if month <= 2 else "春节后调休"
            elif "国庆" in context:
                reason = "国庆前调休" if month <= 9 else "国庆后调休"
            elif "清明" in context:
                reason = "清明节调休"
            elif "劳动" in context or "五一" in context:
                reason = "劳动节调休"

            workdays[d] = reason

        except ValueError:
            pass

    return workdays


def update_cn_holiday_file(
    holidays: dict[date, str],
    workdays: dict[date, str],
    year: int
) -> None:
    """
    更新 backend/services/cn_holiday.py

    Args:
        holidays: 节假日字典
        workdays: 调休工作日字典
        year: 目标年份
    """
    file_path = Path(__file__).parent.parent / "backend" / "services" / "cn_holiday.py"

    if not file_path.exists():
        print(f"文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")

    # 生成新数据条目
    holiday_lines = []
    for d in sorted(holidays.keys()):
        holiday_lines.append(f'    date({d.year}, {d.month}, {d.day}): "{holidays[d]}",')

    workday_lines = []
    for d in sorted(workdays.keys()):
        workday_lines.append(f'    date({d.year}, {d.month}, {d.day}): "{workdays[d]}",')

    # 插入新年份数据到 CN_HOLIDAYS 字典末尾（在最后一个 } 之前）
    holiday_block = f"\n    # {year}年节假日\n" + "\n".join(holiday_lines)
    content = content.replace(
        "\n}",
        holiday_block + "\n}",
        1  # 只替换第一个（CN_HOLIDAYS字典）
    )

    # 插入调休工作日到 WORKDAY_OVERRIDES 字典末尾
    if workday_lines:
        workday_block = f"\n    # {year}年调休工作日\n" + "\n".join(workday_lines)
        # 找到 WORKDAY_OVERRIDES 的结束位置
        pattern = r"(WORKDAY_OVERRIDES = \{[^}]+)\n\}"
        content = re.sub(
            pattern,
            r"\1" + workday_block + "\n}",
            content,
            count=1
        )

    # 写回文件
    file_path.write_text(content, encoding="utf-8")
    print(f"✅ 已更新 {file_path}")
    print(f"   - 新增 {len(holidays)} 个节假日")
    print(f"   - 新增 {len(workdays)} 个调休工作日")


def main():
    """主函数"""
    # 计算次年年份
    next_year = datetime.now().year + 1

    print(f"正在抓取 {next_year} 年节假日安排...")

    # 抓取通知
    notice_text = fetch_holiday_notice(next_year)
    if not notice_text:
        print("⚠️ 抓取失败，请检查国务院官网是否已发布通知", file=sys.stderr)
        sys.exit(1)

    # 解析节假日
    holidays = parse_holidays(notice_text, next_year)
    workdays = parse_workday_overrides(notice_text, next_year)

    if not holidays:
        print("⚠️ 未解析到任何节假日数据", file=sys.stderr)
        sys.exit(1)

    print(f"\n解析结果：")
    print(f"  节假日: {len(holidays)} 个")
    for d, name in sorted(holidays.items()):
        print(f"    - {d} ({name})")

    if workdays:
        print(f"  调休工作日: {len(workdays)} 个")
        for d, reason in sorted(workdays.items()):
            print(f"    - {d} ({reason})")

    # 更新文件
    update_cn_holiday_file(holidays, workdays, next_year)
    print(f"\n🎉 {next_year} 年节假日数据更新完成！")


if __name__ == "__main__":
    main()
