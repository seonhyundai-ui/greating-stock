import os
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import gspread

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


# ============================================================
# Greating Stock Monitor
# version: 0.2.2
#
# Changes
# ------------------------------------------------------------
# 1. CURRENT_STOCK
#    - PREV_STOCK
#    - STOCK_CHANGE
#    - PREV_COLLECTED_AT
#    - LOW_STOCK_LEVEL
#
# 2. STOCK_EVENT
#    - PREV_DUE_DATE
#    - CURRENT_DUE_DATE
#    - CYCLE_RESET
#
# 3. RUN_LOG
#    - CURRENT_DUE_DATE
#    - CURRENT_DUE_DATE_RATIO
#    - LOW_STOCK_COUNT
#    - CRITICAL_STOCK_COUNT
#
# 4. 기존 Google Sheet schema 자동 확장
# ============================================================


VERSION = "0.2.2"

API_URL = "https://www.greating.co.kr/biz/market/getGoodsList"

CATEGORY_ID = 50
EPAGE = 1000

KST = timezone(timedelta(hours=9))


# ============================================================
# Google
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

# v0.2.0에서 사용한 동일한 ID 입력
SPREADSHEET_ID = os.getenv(
    "GREATING_SPREADSHEET_ID",
    "ZXXsaPjURyajBY27VdsN5DKjf9rMDrRcDxq78zA0g",
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ============================================================
# Greating API
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": (
        "https://www.greating.co.kr/market/marketList"
        "?ctgryId=50&page=1"
    ),
}


PARAMS = {
    "page": 1,
    "sPage": 1,
    "ePage": EPAGE,

    "ctgryId": CATEGORY_ID,
    "IL_CTGRY_ID": CATEGORY_ID,

    "SORT_TYPE": "dvMd",
    "SORT_TYPE_P": "dvMd",

    "IL_ITEM_FILTER_ID": "",
    "IL_ITEM_FILTER_ID2": "",
    "AL_FILTER_ID": "",
    "IL_ITEM_FILTER_ID4": "",
    "SAFETY_SCORE_VAL": "",

    "SOLD_OUT_CHECK": "false",

    "UseCache": "N",

    "isPersonal": "N",

    "MIN_PRICE": "",
    "MAX_PRICE": "",
    "HIDE_SUB": "",
}


# ============================================================
# Sheets Schema
#
# 기존 v0.2.0 컬럼 뒤에만 신규 컬럼 추가.
# 기존 행을 깨뜨리지 않기 위함.
# ============================================================

CURRENT_FIELDS = [
    "COLLECTED_AT",
    "IL_ITEM_ID",
    "ITEM_NAME",
    "STOCK",
    "STOCK_STATUS",
    "CTGRY_FULL_NAME_CUST",
    "IL_CTGRY_ID",
    "SALE_END_FLAG",
    "DEL_YN",
    "STATUS",
    "SALE_PRICE",
    "MARKET_PRICE",
    "ITEM_DUE_DATE",
    "ARRIVAL_DATE",

    # v0.2.1
    "PREV_STOCK",
    "STOCK_CHANGE",
    "PREV_COLLECTED_AT",
    "LOW_STOCK_LEVEL",
]


EVENT_FIELDS = [
    "EVENT_AT",
    "EVENT_TYPE",
    "IL_ITEM_ID",
    "ITEM_NAME",
    "PREV_STOCK",
    "CURRENT_STOCK",
    "CTGRY_FULL_NAME_CUST",
    "ITEM_DUE_DATE",

    # v0.2.1
    "PREV_DUE_DATE",
    "CURRENT_DUE_DATE",
]


RUN_LOG_FIELDS = [
    "RUN_AT",
    "VERSION",

    "API_TOTAL",
    "NO_SOLDOUT_TOTAL",

    "COLLECTED_COUNT",
    "UNIQUE_COUNT",
    "SOLD_OUT_COUNT",

    "NEW_SOLD_OUT",
    "RESTOCKED",

    "CYCLE_CHANGED_COUNT",
    "CYCLE_CHANGED_RATIO",

    "NEW_ITEM_COUNT",
    "MISSING_ITEM_COUNT",

    "DUE_DATE_UNKNOWN_COUNT",

    "RUN_STATUS",
    "ELAPSED_SEC",
    "MESSAGE",

    # v0.2.1
    "CURRENT_DUE_DATE",
    "CURRENT_DUE_DATE_RATIO",

    "LOW_STOCK_COUNT",
    "CRITICAL_STOCK_COUNT",
]


# ============================================================
# Utility
# ============================================================

def now_kst():

    return datetime.now(KST)


def now_string():

    return now_kst().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def safe_int(value):

    if value in (None, ""):
        return None

    try:
        return int(float(value))

    except (TypeError, ValueError):
        return None


def normalize_due_date(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value.lower() == "none":
        return None

    return value


def is_active_item(item):

    return (
        item.get("SALE_END_FLAG") == "N"
        and item.get("DEL_YN") == "N"
        and safe_int(
            item.get("STATUS")
        ) == 1
    )


def stock_status(item):

    stock = safe_int(
        item.get("STOCK")
    )

    if stock is None:
        return "UNKNOWN"

    if stock <= 0:
        return "SOLD_OUT"

    return "AVAILABLE"


def low_stock_level(stock):

    stock = safe_int(stock)

    if stock is None:
        return "UNKNOWN"

    if stock <= 0:
        return "SOLD_OUT"

    if stock <= 5:
        return "CRITICAL"

    if stock <= 10:
        return "LOW"

    return "NORMAL"


def column_letter(n):

    result = ""

    while n:

        n, remainder = divmod(
            n - 1,
            26,
        )

        result = (
            chr(65 + remainder)
            + result
        )

    return result


# ============================================================
# Google OAuth
# ============================================================

def get_credentials():

    creds = None

    if TOKEN_FILE.exists():

        creds = (
            Credentials
            .from_authorized_user_file(
                TOKEN_FILE,
                SCOPES,
            )
        )

    if not creds or not creds.valid:

        if (
            creds
            and creds.expired
            and creds.refresh_token
        ):

            creds.refresh(
                Request()
            )

        else:

            if not CREDENTIALS_FILE.exists():

                raise FileNotFoundError(
                    "credentials.json 없음 | "
                    f"{CREDENTIALS_FILE}"
                )

            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    CREDENTIALS_FILE,
                    SCOPES,
                )
            )

            creds = (
                flow.run_local_server(
                    port=0
                )
            )

        TOKEN_FILE.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

    return creds


def connect_google_sheets():

    print(
        "[1/8] Google Sheets 연결"
    )

    creds = get_credentials()

    client = gspread.authorize(
        creds
    )

    spreadsheet = (
        client.open_by_key(
            SPREADSHEET_ID
        )
    )

    print(
        f"      연결 성공: "
        f"{spreadsheet.title}"
    )

    return spreadsheet


# ============================================================
# Worksheet / Schema
# ============================================================

def ensure_worksheet(
    spreadsheet,
    title,
    fields,
):

    try:

        ws = spreadsheet.worksheet(
            title
        )

    except gspread.WorksheetNotFound:

        ws = spreadsheet.add_worksheet(
            title=title,
            rows=1000,
            cols=max(
                len(fields) + 5,
                30,
            ),
        )

        print(
            f"      [CREATE] {title}"
        )

    values = ws.get_all_values()

    is_empty = (
        not values
        or not any(
            any(
                str(cell).strip()
                for cell in row
            )
            for row in values
        )
    )

    if is_empty:

        ws.update(
            range_name="A1",
            values=[fields],
        )

        print(
            f"      {title} 헤더 생성"
        )

        return ws

    current_header = (
        values[0]
        if values
        else []
    )

    # 현재 Schema와 동일
    if current_header == fields:

        print(
            f"      {title} schema 확인"
        )

        return ws

    # --------------------------------------------------------
    # 이전 버전이 현재 버전의 prefix이면
    # 신규 컬럼만 오른쪽에 확장
    # --------------------------------------------------------

    if (
        len(current_header)
        < len(fields)
        and current_header
        == fields[:len(current_header)]
    ):

        last_col = column_letter(
            len(fields)
        )

        ws.update(
            range_name=(
                f"A1:{last_col}1"
            ),
            values=[fields],
        )

        print(
            f"      {title} schema 확장 "
            f"{len(current_header)}"
            f" → {len(fields)} columns"
        )

        return ws

    raise RuntimeError(
        f"{title} 헤더 불일치\n"
        f"expected={fields}\n"
        f"actual={current_header}"
    )


# ============================================================
# Greating API
# ============================================================

def fetch_all_goods():

    print(
        "[2/8] Greating 전체 상품 조회"
    )

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    started = time.perf_counter()

    response = session.get(
        API_URL,
        params=PARAMS,
        timeout=60,
    )

    elapsed = (
        time.perf_counter()
        - started
    )

    print(
        f"      HTTP="
        f"{response.status_code}"
        f" | elapsed="
        f"{elapsed:.2f}s"
    )

    response.raise_for_status()

    data = response.json()

    if (
        data.get("RETURN_CODE")
        != "000000000"
    ):

        raise RuntimeError(
            "RETURN_CODE 오류 | "
            f"{data.get('RETURN_CODE')}"
        )

    return data


# ============================================================
# Snapshot QA
# ============================================================

def validate_snapshot(data):

    print(
        "[3/8] Snapshot QA"
    )

    rows = data.get("rows") or []

    total = safe_int(
        data.get("total")
    )

    no_soldout_total = safe_int(
        data.get(
            "no_soldout_total"
        )
    )

    if total is None:

        raise RuntimeError(
            "API total 없음"
        )

    collected_count = len(rows)

    item_ids = [
        safe_int(
            row.get(
                "IL_ITEM_ID"
            )
        )
        for row in rows
        if row.get(
            "IL_ITEM_ID"
        ) is not None
    ]

    unique_count = len(
        set(item_ids)
    )

    if collected_count != total:

        raise RuntimeError(
            "Snapshot 행 수 불일치 | "
            f"total={total}, "
            f"rows={collected_count}"
        )

    if len(item_ids) != total:

        raise RuntimeError(
            "IL_ITEM_ID 누락 상품 존재"
        )

    if unique_count != total:

        raise RuntimeError(
            "IL_ITEM_ID 중복 | "
            f"total={total}, "
            f"unique={unique_count}"
        )

    sold_out_count = sum(
        1
        for row in rows
        if safe_int(
            row.get("STOCK")
        ) == 0
    )

    if no_soldout_total is not None:

        expected_soldout = (
            total
            - no_soldout_total
        )

        if (
            sold_out_count
            != expected_soldout
        ):

            raise RuntimeError(
                "품절수 검증 실패 | "
                f"STOCK=0 "
                f"{sold_out_count}, "
                f"API="
                f"{expected_soldout}"
            )

    print(
        f"      total={total}"
        f" | unique={unique_count}"
        f" | sold_out="
        f"{sold_out_count}"
    )

    return {
        "rows":
            rows,

        "total":
            total,

        "no_soldout_total":
            no_soldout_total,

        "unique_count":
            unique_count,

        "sold_out_count":
            sold_out_count,
    }


# ============================================================
# API row normalize
# ============================================================

def normalize_rows(
    rows,
    collected_at,
):

    normalized = []

    for item in rows:

        stock = safe_int(
            item.get("STOCK")
        )

        normalized.append({

            "COLLECTED_AT":
                collected_at,

            "IL_ITEM_ID":
                safe_int(
                    item.get(
                        "IL_ITEM_ID"
                    )
                ),

            "ITEM_NAME":
                item.get(
                    "ITEM_NAME"
                ),

            "STOCK":
                stock,

            "STOCK_STATUS":
                stock_status(item),

            "CTGRY_FULL_NAME_CUST":
                item.get(
                    "CTGRY_FULL_NAME_CUST"
                ),

            "IL_CTGRY_ID":
                safe_int(
                    item.get(
                        "IL_CTGRY_ID"
                    )
                ),

            "SALE_END_FLAG":
                item.get(
                    "SALE_END_FLAG"
                ),

            "DEL_YN":
                item.get(
                    "DEL_YN"
                ),

            "STATUS":
                safe_int(
                    item.get(
                        "STATUS"
                    )
                ),

            "SALE_PRICE":
                safe_int(
                    item.get(
                        "SALE_PRICE"
                    )
                ),

            "MARKET_PRICE":
                safe_int(
                    item.get(
                        "MARKET_PRICE"
                    )
                ),

            "ITEM_DUE_DATE":
                normalize_due_date(
                    item.get(
                        "ITEM_DUE_DATE"
                    )
                ),

            "ARRIVAL_DATE":
                item.get(
                    "ARRIVAL_DATE"
                ),

            "PREV_STOCK":
                None,

            "STOCK_CHANGE":
                None,

            "PREV_COLLECTED_AT":
                None,

            "LOW_STOCK_LEVEL":
                low_stock_level(
                    stock
                ),
        })

    return normalized


# ============================================================
# CURRENT_STOCK Read
# ============================================================

def read_current_stock(ws):

    print(
        "[4/8] CURRENT_STOCK 로드"
    )

    values = ws.get_all_values()

    if len(values) <= 1:

        print(
            "      기존 Snapshot 없음"
        )

        return []

    headers = values[0]

    rows = []

    for raw_row in values[1:]:

        if not any(
            str(v).strip()
            for v in raw_row
        ):
            continue

        padded = (
            raw_row
            + [""] * (
                len(headers)
                - len(raw_row)
            )
        )

        row = dict(
            zip(
                headers,
                padded,
            )
        )

        row["IL_ITEM_ID"] = (
            safe_int(
                row.get(
                    "IL_ITEM_ID"
                )
            )
        )

        row["STOCK"] = (
            safe_int(
                row.get(
                    "STOCK"
                )
            )
        )

        row["STATUS"] = (
            safe_int(
                row.get(
                    "STATUS"
                )
            )
        )

        row["ITEM_DUE_DATE"] = (
            normalize_due_date(
                row.get(
                    "ITEM_DUE_DATE"
                )
            )
        )

        rows.append(row)

    print(
        f"      previous="
        f"{len(rows)}"
    )

    return rows


# ============================================================
# Previous stock enrich
# ============================================================

def enrich_current_rows(
    previous_rows,
    current_rows,
):

    previous_map = {
        row["IL_ITEM_ID"]: row
        for row in previous_rows
    }

    for current in current_rows:

        previous = previous_map.get(
            current["IL_ITEM_ID"]
        )

        if previous is None:
            continue

        prev_stock = safe_int(
            previous.get(
                "STOCK"
            )
        )

        current_stock = safe_int(
            current.get(
                "STOCK"
            )
        )

        prev_due = normalize_due_date(
            previous.get(
                "ITEM_DUE_DATE"
            )
        )

        current_due = normalize_due_date(
            current.get(
                "ITEM_DUE_DATE"
            )
        )

        current["PREV_STOCK"] = (
            prev_stock
        )

        current[
            "PREV_COLLECTED_AT"
        ] = previous.get(
            "COLLECTED_AT"
        )

        # ----------------------------------------------------
        # 같은 배송 사이클에서만 재고 증감 계산
        # --------------------------------------------------------

        if (
            prev_due is not None
            and current_due is not None
            and prev_due == current_due
            and prev_stock is not None
            and current_stock is not None
        ):

            current["STOCK_CHANGE"] = (
                current_stock
                - prev_stock
            )

        else:

            current["STOCK_CHANGE"] = None

    return current_rows


# ============================================================
# Current mall delivery date
# ============================================================

def get_current_due_date(rows):

    due_dates = [
        normalize_due_date(
            row.get(
                "ITEM_DUE_DATE"
            )
        )
        for row in rows
    ]

    due_dates = [
        x
        for x in due_dates
        if x is not None
    ]

    if not due_dates:

        return None, 0.0

    counter = Counter(
        due_dates
    )

    due_date, count = (
        counter.most_common(1)[0]
    )

    ratio = (
        count
        / len(due_dates)
    )

    return (
        due_date,
        ratio,
    )


# ============================================================
# Event detection
# ============================================================

def detect_events(
    previous_rows,
    current_rows,
    event_at,
):

    previous_map = {
        row["IL_ITEM_ID"]: row
        for row in previous_rows
    }

    current_map = {
        row["IL_ITEM_ID"]: row
        for row in current_rows
    }

    events = []

    new_sold_out = 0
    restocked = 0

    cycle_changed_count = 0
    due_date_unknown_count = 0
    new_item_count = 0

    for (
        item_id,
        current,
    ) in current_map.items():

        previous = (
            previous_map.get(
                item_id
            )
        )

        if previous is None:

            new_item_count += 1
            continue

        prev_stock = safe_int(
            previous.get(
                "STOCK"
            )
        )

        current_stock = safe_int(
            current.get(
                "STOCK"
            )
        )

        prev_due = (
            normalize_due_date(
                previous.get(
                    "ITEM_DUE_DATE"
                )
            )
        )

        current_due = (
            normalize_due_date(
                current.get(
                    "ITEM_DUE_DATE"
                )
            )
        )

        # ----------------------------------------------------
        # 배송일 확인 불가
        # --------------------------------------------------------

        if (
            prev_due is None
            or current_due is None
        ):

            due_date_unknown_count += 1
            continue

        # ----------------------------------------------------
        # 배송 사이클 변경
        # --------------------------------------------------------

        if prev_due != current_due:

            cycle_changed_count += 1

            # 이전 배송 사이클에서 품절 상태였던 상품만
            # CYCLE_RESET 이벤트를 남긴다.
            #
            # 이전 품절 Episode를 종료하기 위함.
            if prev_stock == 0:

                events.append({

                    "EVENT_AT":
                        event_at,

                    "EVENT_TYPE":
                        "CYCLE_RESET",

                    "IL_ITEM_ID":
                        item_id,

                    "ITEM_NAME":
                        current.get(
                            "ITEM_NAME"
                        ),

                    "PREV_STOCK":
                        prev_stock,

                    "CURRENT_STOCK":
                        current_stock,

                    "CTGRY_FULL_NAME_CUST":
                        current.get(
                            "CTGRY_FULL_NAME_CUST"
                        ),

                    # 기존 컬럼 호환
                    "ITEM_DUE_DATE":
                        current_due,

                    "PREV_DUE_DATE":
                        prev_due,

                    "CURRENT_DUE_DATE":
                        current_due,
                })

            continue

        # ----------------------------------------------------
        # 판매종료 / 삭제 제외
        # --------------------------------------------------------

        if not is_active_item(
            current
        ):

            continue

        if (
            prev_stock is None
            or current_stock is None
        ):
            continue

        # ----------------------------------------------------
        # 신규 품절
        # --------------------------------------------------------

        if (
            prev_stock > 0
            and current_stock == 0
        ):

            event_type = (
                "SOLD_OUT"
            )

            new_sold_out += 1

        # ----------------------------------------------------
        # 재입고
        # --------------------------------------------------------

        elif (
            prev_stock == 0
            and current_stock > 0
        ):

            event_type = (
                "RESTOCKED"
            )

            restocked += 1

        else:
            continue

        events.append({

            "EVENT_AT":
                event_at,

            "EVENT_TYPE":
                event_type,

            "IL_ITEM_ID":
                item_id,

            "ITEM_NAME":
                current.get(
                    "ITEM_NAME"
                ),

            "PREV_STOCK":
                prev_stock,

            "CURRENT_STOCK":
                current_stock,

            "CTGRY_FULL_NAME_CUST":
                current.get(
                    "CTGRY_FULL_NAME_CUST"
                ),

            "ITEM_DUE_DATE":
                current_due,

            "PREV_DUE_DATE":
                prev_due,

            "CURRENT_DUE_DATE":
                current_due,
        })

    missing_item_count = len(
        set(previous_map)
        - set(current_map)
    )

    compared_count = max(
        len(current_map)
        - new_item_count,
        1,
    )

    cycle_changed_ratio = (
        cycle_changed_count
        / compared_count
    )

    return {

        "events":
            events,

        "new_sold_out":
            new_sold_out,

        "restocked":
            restocked,

        "cycle_changed_count":
            cycle_changed_count,

        "cycle_changed_ratio":
            cycle_changed_ratio,

        "new_item_count":
            new_item_count,

        "missing_item_count":
            missing_item_count,

        "due_date_unknown_count":
            due_date_unknown_count,
    }


# ============================================================
# Google Sheet Write
# ============================================================

def write_current_stock(
    ws,
    rows,
):

    matrix = [
        CURRENT_FIELDS
    ]

    for row in rows:

        matrix.append([
            (
                row.get(field, "")
                if row.get(field)
                is not None
                else ""
            )
            for field
            in CURRENT_FIELDS
        ])

    existing = (
        ws.get_all_values()
    )

    old_row_count = len(
        existing
    )

    new_row_count = len(
        matrix
    )

    last_col = column_letter(
        len(CURRENT_FIELDS)
    )

    ws.update(
        range_name=(
            f"A1:"
            f"{last_col}"
            f"{new_row_count}"
        ),
        values=matrix,
        value_input_option="RAW",
    )

    if (
        old_row_count
        > new_row_count
    ):

        ws.batch_clear([
            (
                f"A"
                f"{new_row_count + 1}:"
                f"{last_col}"
                f"{old_row_count}"
            )
        ])


def append_sheet_rows(
    ws,
    fields,
    rows,
):

    if not rows:
        return

    values = []

    for row in rows:

        values.append([
            (
                row.get(field, "")
                if row.get(field)
                is not None
                else ""
            )
            for field
            in fields
        ])

    ws.append_rows(
        values,
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 80)

    print(
        f"Greating Stock Monitor "
        f"v{VERSION}"
    )

    print("=" * 80)

    started = (
        time.perf_counter()
    )

    run_at = now_string()

    run_log_ws = None

    try:

        # ====================================================
        # 1. Google
        # ====================================================

        spreadsheet = (
            connect_google_sheets()
        )

        current_ws = (
            ensure_worksheet(
                spreadsheet,
                "CURRENT_STOCK",
                CURRENT_FIELDS,
            )
        )

        event_ws = (
            ensure_worksheet(
                spreadsheet,
                "STOCK_EVENT",
                EVENT_FIELDS,
            )
        )

        run_log_ws = (
            ensure_worksheet(
                spreadsheet,
                "RUN_LOG",
                RUN_LOG_FIELDS,
            )
        )

        # ====================================================
        # 2. API
        # ====================================================

        data = (
            fetch_all_goods()
        )

        # ====================================================
        # 3. QA
        # ====================================================

        qa = (
            validate_snapshot(
                data
            )
        )

        current_rows = (
            normalize_rows(
                qa["rows"],
                run_at,
            )
        )

        # ====================================================
        # 4. Previous
        # ====================================================

        previous_rows = (
            read_current_stock(
                current_ws
            )
        )

        # 이전 재고 정보 결합
        current_rows = (
            enrich_current_rows(
                previous_rows,
                current_rows,
            )
        )

        # ====================================================
        # 현재 몰 배송일
        # ====================================================

        (
            current_due_date,
            current_due_ratio,
        ) = get_current_due_date(
            current_rows
        )

        # ====================================================
        # 품절 임박
        # ====================================================

        low_stock_count = sum(
            1
            for row in current_rows
            if (
                is_active_item(row)
                and safe_int(
                    row.get("STOCK")
                ) is not None
                and 1
                <= safe_int(
                    row.get("STOCK")
                )
                <= 10
            )
        )

        critical_stock_count = sum(
            1
            for row in current_rows
            if (
                is_active_item(row)
                and safe_int(
                    row.get("STOCK")
                ) is not None
                and 1
                <= safe_int(
                    row.get("STOCK")
                )
                <= 5
            )
        )

        # ====================================================
        # 5. Events
        # ====================================================

        print(
            "[5/8] 재고 이벤트 비교"
        )

        if not previous_rows:

            result = {

                "events": [],

                "new_sold_out": 0,

                "restocked": 0,

                "cycle_changed_count": 0,

                "cycle_changed_ratio": 0.0,

                "new_item_count": 0,

                "missing_item_count": 0,

                "due_date_unknown_count": 0,
            }

            run_status = (
                "BASELINE_CREATED"
            )

            message = (
                "Google Sheets 최초 "
                "기준 Snapshot 생성"
            )

            print(
                "      기준 Snapshot 없음"
            )

        else:

            result = (
                detect_events(
                    previous_rows,
                    current_rows,
                    run_at,
                )
            )

            run_status = "SUCCESS"

            message = (
                f"SOLD_OUT="
                f"{result['new_sold_out']}, "
                f"RESTOCKED="
                f"{result['restocked']}, "
                f"CYCLE_CHANGED="
                f"{result['cycle_changed_count']}"
            )

            print(
                f"      신규품절="
                f"{result['new_sold_out']}"
            )

            print(
                f"      재입고="
                f"{result['restocked']}"
            )

            print(
                f"      배송일변경="
                f"{result['cycle_changed_count']}"
                f" "
                f"("
                f"{result['cycle_changed_ratio']:.1%}"
                f")"
            )

            print(
                f"      신규상품="
                f"{result['new_item_count']}"
            )

            print(
                f"      목록이탈="
                f"{result['missing_item_count']}"
            )

        # ====================================================
        # 6. Event Write
        # ====================================================

        print(
            "[6/8] STOCK_EVENT 저장"
        )

        append_sheet_rows(
            event_ws,
            EVENT_FIELDS,
            result["events"],
        )

        if not result["events"]:

            print(
                "      저장할 이벤트 없음"
            )

        else:

            for event in (
                result["events"]
            ):

                print(
                    f"      "
                    f"{event['EVENT_TYPE']}"
                    f" | "
                    f"{event['IL_ITEM_ID']}"
                    f" | "
                    f"{event['ITEM_NAME']}"
                    f" | "
                    f"{event['PREV_STOCK']}"
                    f" → "
                    f"{event['CURRENT_STOCK']}"
                )

        # ====================================================
        # 7. Current Write
        # ====================================================

        print(
            "[7/8] CURRENT_STOCK 갱신"
        )

        write_current_stock(
            current_ws,
            current_rows,
        )

        # ====================================================
        # 8. Run Log
        # ====================================================

        total_elapsed = (
            time.perf_counter()
            - started
        )

        log_row = {

            "RUN_AT":
                run_at,

            "VERSION":
                VERSION,

            "API_TOTAL":
                qa["total"],

            "NO_SOLDOUT_TOTAL":
                qa[
                    "no_soldout_total"
                ],

            "COLLECTED_COUNT":
                len(current_rows),

            "UNIQUE_COUNT":
                qa[
                    "unique_count"
                ],

            "SOLD_OUT_COUNT":
                qa[
                    "sold_out_count"
                ],

            "NEW_SOLD_OUT":
                result[
                    "new_sold_out"
                ],

            "RESTOCKED":
                result[
                    "restocked"
                ],

            "CYCLE_CHANGED_COUNT":
                result[
                    "cycle_changed_count"
                ],

            "CYCLE_CHANGED_RATIO":
                round(
                    result[
                        "cycle_changed_ratio"
                    ],
                    4,
                ),

            "NEW_ITEM_COUNT":
                result[
                    "new_item_count"
                ],

            "MISSING_ITEM_COUNT":
                result[
                    "missing_item_count"
                ],

            "DUE_DATE_UNKNOWN_COUNT":
                result[
                    "due_date_unknown_count"
                ],

            "RUN_STATUS":
                run_status,

            "ELAPSED_SEC":
                round(
                    total_elapsed,
                    2,
                ),

            "MESSAGE":
                message,

            "CURRENT_DUE_DATE":
                current_due_date,

            "CURRENT_DUE_DATE_RATIO":
                round(
                    current_due_ratio,
                    4,
                ),

            "LOW_STOCK_COUNT":
                low_stock_count,

            "CRITICAL_STOCK_COUNT":
                critical_stock_count,
        }

        print(
            "[8/8] RUN_LOG 저장"
        )

        append_sheet_rows(
            run_log_ws,
            RUN_LOG_FIELDS,
            [log_row],
        )

        # ====================================================
        # Result
        # ====================================================

        print()
        print("=" * 80)
        print("RESULT")
        print("=" * 80)

        print(
            f"상태             : "
            f"{run_status}"
        )

        print(
            f"현재 배송일      : "
            f"{current_due_date}"
            f" "
            f"({current_due_ratio:.1%})"
        )

        print(
            f"전체 상품        : "
            f"{qa['total']}"
        )

        print(
            f"현재 품절        : "
            f"{qa['sold_out_count']}"
        )

        print(
            f"품절 임박 1~10   : "
            f"{low_stock_count}"
        )

        print(
            f"매우 임박 1~5    : "
            f"{critical_stock_count}"
        )

        print(
            f"신규 품절        : "
            f"{result['new_sold_out']}"
        )

        print(
            f"재입고           : "
            f"{result['restocked']}"
        )

        print(
            f"배송일 변경      : "
            f"{result['cycle_changed_count']}"
            f" "
            f"("
            f"{result['cycle_changed_ratio']:.1%}"
            f")"
        )

        print(
            f"실행시간         : "
            f"{total_elapsed:.2f}s"
        )

        print()
        print(
            "✅ Google Sheets 저장 완료"
        )

    except Exception as e:

        total_elapsed = (
            time.perf_counter()
            - started
        )

        print()
        print("=" * 80)
        print("ERROR")
        print("=" * 80)

        print(
            f"{type(e).__name__}: "
            f"{e}"
        )

        if run_log_ws is not None:

            try:

                error_log = {
                    field: ""
                    for field
                    in RUN_LOG_FIELDS
                }

                error_log.update({

                    "RUN_AT":
                        run_at,

                    "VERSION":
                        VERSION,

                    "RUN_STATUS":
                        "ERROR",

                    "ELAPSED_SEC":
                        round(
                            total_elapsed,
                            2,
                        ),

                    "MESSAGE":
                        (
                            f"{type(e).__name__}: "
                            f"{e}"
                        ),
                })

                append_sheet_rows(
                    run_log_ws,
                    RUN_LOG_FIELDS,
                    [error_log],
                )

            except Exception:
                pass

        raise


if __name__ == "__main__":
    main()