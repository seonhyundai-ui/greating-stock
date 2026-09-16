import hmac

import pandas as pd
import streamlit as st
import gspread

from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


# ============================================================
# Greating Stock Monitor Dashboard
# version: 0.1.2
#
# Data Source
# ------------------------------------------------------------
# Google Sheets
#   - CURRENT_STOCK
#   - STOCK_EVENT
#   - RUN_LOG
#
# v0.1.2
# ------------------------------------------------------------
# 1. 첫 화면 비밀번호 로그인 추가
# 2. 로그인 전 Google Sheets 데이터 접근 차단
# 3. 로그인 세션 유지 / 로그아웃 버튼 추가
# 4. v0.1.1 대시보드 기능 전체 유지
# ============================================================


VERSION = "0.1.2"

KST = timezone(
    timedelta(hours=9)
)

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

CREDENTIALS_FILE = (
    BASE_DIR
    / "credentials.json"
)

TOKEN_FILE = (
    BASE_DIR
    / "token.json"
)


# ============================================================
# Google Spreadsheet
# stock_monitor_v0.2.1.py와 동일한 ID 입력
# ============================================================

SPREADSHEET_ID = "1MwZXXsaPjURyajBY27VdsN5DKjf9rMDrRcDxq78zA0g"


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ============================================================
# Streamlit Page
# ============================================================

st.set_page_config(
    page_title=(
        "Greating Stock Monitor"
    ),
    page_icon="📦",
    layout="wide",
)


# ============================================================
# Login
# ============================================================

def check_login():

    if st.session_state.get(
        "authenticated",
        False,
    ):
        return True

    spacer_left, login_col, spacer_right = (
        st.columns([1, 1.2, 1])
    )

    with login_col:

        st.title(
            "📦 Greating Stock Monitor"
        )

        st.caption(
            "그리팅 건강마켓 재고 및 품절 모니터링"
        )

        st.markdown(
            "접근을 위해 비밀번호를 입력해주세요."
        )

        with st.form(
            "login_form",
            clear_on_submit=False,
        ):

            password = st.text_input(
                "비밀번호",
                type="password",
                placeholder="비밀번호 입력",
            )

            submitted = (
                st.form_submit_button(
                    "로그인",
                    use_container_width=True,
                )
            )

        if submitted:

            try:
                correct_password = str(
                    st.secrets[
                        "APP_PASSWORD"
                    ]
                )

            except Exception:

                st.error(
                    "APP_PASSWORD 설정이 없습니다. "
                    "Streamlit Secrets를 확인해주세요."
                )

                return False

            if hmac.compare_digest(
                str(password),
                correct_password,
            ):

                st.session_state[
                    "authenticated"
                ] = True

                st.rerun()

            else:

                st.error(
                    "비밀번호가 올바르지 않습니다."
                )

    return False


if not check_login():
    st.stop()


# ============================================================
# Utility
# ============================================================

def now_kst():

    return datetime.now(
        KST
    )


def safe_int(value):

    if value in (
        None,
        "",
    ):
        return None

    try:
        return int(
            float(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def normalize_text(value):

    if pd.isna(value):
        return ""

    return str(
        value
    ).strip()


def format_stock_change(
    value,
):

    if pd.isna(value):
        return "-"

    try:
        value = int(
            float(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return "-"

    if value > 0:
        return f"+{value}"

    return str(value)


def format_stock_value(
    value,
):

    if pd.isna(value):
        return ""

    try:
        return str(
            int(float(value))
        )

    except (
        TypeError,
        ValueError,
    ):
        return str(value)


def human_duration(
    start_dt,
):

    """
    현재까지의 품절 지속시간 계산
    """

    if pd.isna(start_dt):

        return (
            "기준점 이전 / 미확인"
        )

    now = pd.Timestamp.now(
        tz="Asia/Seoul"
    )

    if start_dt.tzinfo is None:

        start_dt = (
            start_dt.tz_localize(
                "Asia/Seoul"
            )
        )

    delta = (
        now
        - start_dt
    )

    total_minutes = max(
        int(
            delta.total_seconds()
            // 60
        ),
        0,
    )

    days = (
        total_minutes
        // 1440
    )

    hours = (
        total_minutes
        % 1440
    ) // 60

    minutes = (
        total_minutes
        % 60
    )

    if days > 0:

        return (
            f"{days}일 "
            f"{hours}시간"
        )

    if hours > 0:

        return (
            f"{hours}시간 "
            f"{minutes}분"
        )

    return (
        f"{minutes}분"
    )


def extract_main_category(
    path,
):

    """
    예:
    건강마켓 / 식재료 / 계란
        -> 식재료
    """

    if not path:
        return "기타"

    parts = [
        x.strip()
        for x
        in str(path).split("/")
        if x.strip()
    ]

    if len(parts) >= 2:
        return parts[1]

    if parts:
        return parts[0]

    return "기타"


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

    if (
        not creds
        or not creds.valid
    ):

        if (
            creds
            and creds.expired
            and creds.refresh_token
        ):

            creds.refresh(
                Request()
            )

        else:

            if (
                not
                CREDENTIALS_FILE.exists()
            ):

                raise FileNotFoundError(
                    "credentials.json이 없습니다."
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


@st.cache_resource
def get_spreadsheet():

    creds = (
        get_credentials()
    )

    client = (
        gspread.authorize(
            creds
        )
    )

    return (
        client.open_by_key(
            SPREADSHEET_ID
        )
    )


# ============================================================
# Google Sheet Load
# ============================================================

@st.cache_data(
    ttl=60
)
def load_sheet(
    sheet_name,
):

    spreadsheet = (
        get_spreadsheet()
    )

    ws = (
        spreadsheet
        .worksheet(
            sheet_name
        )
    )

    values = (
        ws.get_all_records()
    )

    return pd.DataFrame(
        values
    )


def load_all_data():

    current_df = (
        load_sheet(
            "CURRENT_STOCK"
        )
    )

    event_df = (
        load_sheet(
            "STOCK_EVENT"
        )
    )

    run_df = (
        load_sheet(
            "RUN_LOG"
        )
    )

    return (
        current_df,
        event_df,
        run_df,
    )


# ============================================================
# Data Cleaning
# ============================================================

def prepare_current(
    df,
):

    if df.empty:
        return df

    df = df.copy()

    numeric_columns = [
        "IL_ITEM_ID",
        "STOCK",
        "PREV_STOCK",
        "STOCK_CHANGE",
        "STATUS",
        "SALE_PRICE",
        "MARKET_PRICE",
    ]

    for col in numeric_columns:

        if col in df.columns:

            df[col] = (
                pd.to_numeric(
                    df[col],
                    errors="coerce",
                )
            )

    if (
        "COLLECTED_AT"
        in df.columns
    ):

        df[
            "COLLECTED_AT"
        ] = (
            pd.to_datetime(
                df[
                    "COLLECTED_AT"
                ],
                errors="coerce",
            )
        )

    if (
        "PREV_COLLECTED_AT"
        in df.columns
    ):

        df[
            "PREV_COLLECTED_AT"
        ] = (
            pd.to_datetime(
                df[
                    "PREV_COLLECTED_AT"
                ],
                errors="coerce",
            )
        )

    if (
        "CTGRY_FULL_NAME_CUST"
        in df.columns
    ):

        df[
            "MAIN_CATEGORY"
        ] = (
            df[
                "CTGRY_FULL_NAME_CUST"
            ]
            .apply(
                extract_main_category
            )
        )

    return df


def prepare_events(
    df,
):

    if df.empty:
        return df

    df = df.copy()

    numeric_columns = [
        "IL_ITEM_ID",
        "PREV_STOCK",
        "CURRENT_STOCK",
    ]

    for col in numeric_columns:

        if col in df.columns:

            df[col] = (
                pd.to_numeric(
                    df[col],
                    errors="coerce",
                )
            )

    if (
        "EVENT_AT"
        in df.columns
    ):

        df[
            "EVENT_AT"
        ] = (
            pd.to_datetime(
                df[
                    "EVENT_AT"
                ],
                errors="coerce",
            )
        )

    if (
        "CTGRY_FULL_NAME_CUST"
        in df.columns
    ):

        df[
            "MAIN_CATEGORY"
        ] = (
            df[
                "CTGRY_FULL_NAME_CUST"
            ]
            .apply(
                extract_main_category
            )
        )

    return df


def prepare_run_log(
    df,
):

    if df.empty:
        return df

    df = df.copy()

    if (
        "RUN_AT"
        in df.columns
    ):

        df[
            "RUN_AT"
        ] = (
            pd.to_datetime(
                df[
                    "RUN_AT"
                ],
                errors="coerce",
            )
        )

    numeric_columns = [
        "API_TOTAL",
        "SOLD_OUT_COUNT",
        "NEW_SOLD_OUT",
        "RESTOCKED",
        "CYCLE_CHANGED_COUNT",
        "CYCLE_CHANGED_RATIO",
        "LOW_STOCK_COUNT",
        "CRITICAL_STOCK_COUNT",
    ]

    for col in numeric_columns:

        if col in df.columns:

            df[col] = (
                pd.to_numeric(
                    df[col],
                    errors="coerce",
                )
            )

    return df


# ============================================================
# 현재 품절 시작 시각 계산
# ============================================================

def build_soldout_start_map(
    current_df,
    event_df,
):

    result = {}

    if (
        current_df.empty
        or event_df.empty
    ):

        return result

    if (
        "EVENT_TYPE"
        not in event_df.columns
    ):

        return result

    soldout_events = (
        event_df[
            event_df[
                "EVENT_TYPE"
            ]
            == "SOLD_OUT"
        ]
        .copy()
    )

    if soldout_events.empty:
        return result

    for (
        _,
        current,
    ) in current_df.iterrows():

        item_id = (
            current.get(
                "IL_ITEM_ID"
            )
        )

        due_date = (
            normalize_text(
                current.get(
                    "ITEM_DUE_DATE"
                )
            )
        )

        subset = (
            soldout_events[
                soldout_events[
                    "IL_ITEM_ID"
                ]
                == item_id
            ]
            .copy()
        )

        if (
            "CURRENT_DUE_DATE"
            in subset.columns
            and due_date
        ):

            subset = subset[
                subset[
                    "CURRENT_DUE_DATE"
                ]
                .astype(str)
                == due_date
            ]

        if subset.empty:
            continue

        last_event = (
            subset
            .sort_values(
                "EVENT_AT"
            )
            .iloc[-1]
        )

        result[
            item_id
        ] = (
            last_event[
                "EVENT_AT"
            ]
        )

    return result


# ============================================================
# Header
# ============================================================

st.title(
    "📦 Greating Stock Monitor"
)

st.caption(
    f"Dashboard v{VERSION} · "
    "건강마켓 상품 재고 및 품절 모니터링"
)


# ============================================================
# Refresh / Logout
# ============================================================

top_left, refresh_col, logout_col = (
    st.columns(
        [5, 1, 1]
    )
)

with refresh_col:

    if st.button(
        "↻ 새로고침",
        use_container_width=True,
    ):

        st.cache_data.clear()

        st.rerun()


with logout_col:

    if st.button(
        "로그아웃",
        use_container_width=True,
    ):

        st.session_state[
            "authenticated"
        ] = False

        st.rerun()


# ============================================================
# Load
# ============================================================

try:

    (
        current_df,
        event_df,
        run_df,
    ) = load_all_data()

except Exception as e:

    st.error(
        "Google Sheets 데이터를 "
        "불러오지 못했습니다."
    )

    st.exception(e)

    st.stop()


current_df = (
    prepare_current(
        current_df
    )
)

event_df = (
    prepare_events(
        event_df
    )
)

run_df = (
    prepare_run_log(
        run_df
    )
)


if current_df.empty:

    st.warning(
        "CURRENT_STOCK 데이터가 없습니다."
    )

    st.stop()


# ============================================================
# Latest Run
# ============================================================

latest_run = None

if not run_df.empty:

    valid_runs = (
        run_df[
            run_df[
                "RUN_AT"
            ].notna()
        ]
        .copy()
    )

    if not valid_runs.empty:

        latest_run = (
            valid_runs
            .sort_values(
                "RUN_AT"
            )
            .iloc[-1]
        )


# ============================================================
# Current Delivery Date
# ============================================================

current_due_date = None
current_due_ratio = None

if latest_run is not None:

    if (
        "CURRENT_DUE_DATE"
        in latest_run.index
    ):

        current_due_date = (
            latest_run.get(
                "CURRENT_DUE_DATE"
            )
        )

    if (
        "CURRENT_DUE_DATE_RATIO"
        in latest_run.index
    ):

        current_due_ratio = (
            latest_run.get(
                "CURRENT_DUE_DATE_RATIO"
            )
        )


if (
    current_due_date is None
    or pd.isna(
        current_due_date
    )
    or str(
        current_due_date
    ).strip() == ""
):

    if (
        "ITEM_DUE_DATE"
        in current_df.columns
    ):

        due_values = (
            current_df[
                "ITEM_DUE_DATE"
            ]
            .dropna()
            .astype(str)
        )

        if not due_values.empty:

            current_due_date = (
                due_values
                .value_counts()
                .idxmax()
            )


# ============================================================
# Active Products
# ============================================================

active_mask = (
    current_df[
        "SALE_END_FLAG"
    ]
    .astype(str)
    == "N"
)

active_mask &= (
    current_df[
        "DEL_YN"
    ]
    .astype(str)
    == "N"
)

active_mask &= (
    current_df[
        "STATUS"
    ]
    == 1
)


active_df = (
    current_df[
        active_mask
    ]
    .copy()
)


# ============================================================
# KPI
# ============================================================

total_count = len(
    active_df
)


soldout_df = (
    active_df[
        active_df[
            "STOCK"
        ]
        == 0
    ]
    .copy()
)


soldout_count = len(
    soldout_df
)


soldout_rate = (
    soldout_count
    / total_count
    * 100
    if total_count
    else 0
)


low_stock_df = (
    active_df[
        (
            active_df[
                "STOCK"
            ]
            >= 1
        )
        &
        (
            active_df[
                "STOCK"
            ]
            <= 10
        )
    ]
    .copy()
)


low_stock_count = len(
    low_stock_df
)


# ============================================================
# Today Events
# ============================================================

today = (
    pd.Timestamp.now(
        tz="Asia/Seoul"
    )
    .date()
)


today_events = (
    event_df.copy()
)


if (
    not today_events.empty
    and "EVENT_AT"
    in today_events.columns
):

    today_events = (
        today_events[
            today_events[
                "EVENT_AT"
            ].dt.date
            == today
        ]
        .copy()
    )


today_soldout = 0
today_restocked = 0


if (
    not today_events.empty
    and "EVENT_TYPE"
    in today_events.columns
):

    today_soldout = len(
        today_events[
            today_events[
                "EVENT_TYPE"
            ]
            == "SOLD_OUT"
        ]
    )

    today_restocked = len(
        today_events[
            today_events[
                "EVENT_TYPE"
            ]
            == "RESTOCKED"
        ]
    )


# ============================================================
# Last Run
# ============================================================

last_run_at = None
last_status = "-"


if latest_run is not None:

    last_run_at = (
        latest_run.get(
            "RUN_AT"
        )
    )

    last_status = str(
        latest_run.get(
            "RUN_STATUS",
            "-",
        )
    )


if (
    last_run_at is not None
    and pd.notna(
        last_run_at
    )
):

    last_run_text = (
        last_run_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

else:

    last_run_text = "-"


if last_status == "SUCCESS":

    status_text = (
        "🟢 정상"
    )

elif (
    last_status
    == "BASELINE_CREATED"
):

    status_text = (
        "🟡 기준 생성"
    )

elif last_status == "ERROR":

    status_text = (
        "🔴 오류"
    )

else:

    status_text = (
        f"⚪ {last_status}"
    )


# ============================================================
# Top Status
# ============================================================

st.markdown(
    f"""
**현재 배송일:** `{current_due_date or '-'}`  
**최근 업데이트:** `{last_run_text}` · {status_text}
"""
)


# ============================================================
# 운영 현황
# ============================================================

st.subheader(
    "운영 현황"
)


k1, k2, k3, k4 = (
    st.columns(4)
)


k1.metric(
    "전체 상품",
    f"{total_count:,}개",
)


k2.metric(
    "현재 품절",
    f"{soldout_count:,}개",
)


k3.metric(
    "품절률",
    f"{soldout_rate:.1f}%",
)


k4.metric(
    "품절 임박",
    f"{low_stock_count:,}개",
)


k5, k6, k7, k8 = (
    st.columns(4)
)


k5.metric(
    "오늘 신규 품절",
    f"{today_soldout:,}개",
)


k6.metric(
    "오늘 재입고",
    f"{today_restocked:,}개",
)


if latest_run is not None:

    cycle_count = (
        safe_int(
            latest_run.get(
                "CYCLE_CHANGED_COUNT"
            )
        )
        or 0
    )

else:

    cycle_count = 0


k7.metric(
    "최근 배송일 변경",
    f"{cycle_count:,}개",
)


k8.metric(
    "수집 상태",
    status_text,
)


# ============================================================
# 상품 검색 / 필터
# ============================================================

st.markdown(
    "#### 🔎 상품 검색"
)


filter_col1, filter_col2 = (
    st.columns(
        [1, 2]
    )
)


category_options = [
    "전체"
]


if (
    "MAIN_CATEGORY"
    in active_df.columns
):

    categories = (
        active_df[
            "MAIN_CATEGORY"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    category_options += sorted(
        categories
    )


with filter_col1:

    selected_category = (
        st.selectbox(
            "카테고리",
            category_options,
            index=0,
        )
    )


with filter_col2:

    product_keyword = (
        st.text_input(
            "상품명 검색",
            placeholder=(
                "예: 우유, 도시락, 샐러드"
            ),
        )
    )


def apply_product_filter(
    df,
):

    result = df.copy()

    if result.empty:
        return result

    # 카테고리
    if (
        selected_category
        != "전체"
        and "MAIN_CATEGORY"
        in result.columns
    ):

        result = result[
            result[
                "MAIN_CATEGORY"
            ]
            == selected_category
        ]

    # 상품명
    keyword = (
        product_keyword
        .strip()
    )

    if (
        keyword
        and "ITEM_NAME"
        in result.columns
    ):

        result = result[
            result[
                "ITEM_NAME"
            ]
            .astype(str)
            .str.contains(
                keyword,
                case=False,
                na=False,
                regex=False,
            )
        ]

    return result


if (
    selected_category
    != "전체"
    or product_keyword.strip()
):

    filter_text = []

    if (
        selected_category
        != "전체"
    ):

        filter_text.append(
            "카테고리: "
            f"{selected_category}"
        )

    if product_keyword.strip():

        filter_text.append(
            "상품명: "
            f"'{product_keyword.strip()}'"
        )

    st.caption(
        "검색 적용 중 · "
        + " / ".join(
            filter_text
        )
    )


st.divider()


# ============================================================
# 현재 품절 상품
# ============================================================

st.subheader(
    "🔴 현재 품절 상품"
)


filtered_soldout_df = (
    apply_product_filter(
        soldout_df
    )
)


soldout_start_map = (
    build_soldout_start_map(
        filtered_soldout_df,
        event_df,
    )
)


if filtered_soldout_df.empty:

    st.info(
        "검색 조건에 해당하는 "
        "현재 품절 상품이 없습니다."
    )

else:

    filtered_soldout_df = (
        filtered_soldout_df
        .copy()
    )

    filtered_soldout_df[
        "품절 시작"
    ] = (
        filtered_soldout_df[
            "IL_ITEM_ID"
        ]
        .map(
            soldout_start_map
        )
    )

    filtered_soldout_df[
        "품절 지속"
    ] = (
        filtered_soldout_df[
            "품절 시작"
        ]
        .apply(
            human_duration
        )
    )

    filtered_soldout_df[
        "품절 시작 표시"
    ] = (
        filtered_soldout_df[
            "품절 시작"
        ]
        .apply(
            lambda x: (
                x.strftime(
                    "%m-%d %H:%M"
                )
                if pd.notna(x)
                else (
                    "기준점 이전 / 미확인"
                )
            )
        )
    )

    # 최근 새로 품절된 상품 우선
    soldout_view = (
        filtered_soldout_df
        .sort_values(
            "품절 시작",
            ascending=False,
            na_position="last",
        )
        [
            [
                "IL_ITEM_ID",
                "ITEM_NAME",
                "MAIN_CATEGORY",
                "ITEM_DUE_DATE",
                "품절 시작 표시",
                "품절 지속",
                "PREV_STOCK",
            ]
        ]
        .rename(
            columns={
                "IL_ITEM_ID":
                    "상품ID",

                "ITEM_NAME":
                    "상품명",

                "MAIN_CATEGORY":
                    "카테고리",

                "ITEM_DUE_DATE":
                    "배송일",

                "품절 시작 표시":
                    "품절 시작",

                "품절 지속":
                    "지속시간",

                "PREV_STOCK":
                    "직전 재고",
            }
        )
    )

    st.dataframe(
        soldout_view,
        use_container_width=True,
        hide_index=True,
        height=500,
    )


st.divider()


# ============================================================
# 품절 임박 상품
# ============================================================

st.subheader(
    "⚠️ 품절 임박 상품"
)

st.caption(
    "CRITICAL 1~5개 / LOW 6~10개"
)


filtered_low_stock_df = (
    apply_product_filter(
        low_stock_df
    )
)


if filtered_low_stock_df.empty:

    st.info(
        "검색 조건에 해당하는 "
        "품절 임박 상품이 없습니다."
    )

else:

    filtered_low_stock_df = (
        filtered_low_stock_df
        .copy()
    )

    filtered_low_stock_df[
        "재고 증감"
    ] = (
        filtered_low_stock_df[
            "STOCK_CHANGE"
        ]
        .apply(
            format_stock_change
        )
    )

    filtered_low_stock_df[
        "위험도순"
    ] = (
        filtered_low_stock_df[
            "LOW_STOCK_LEVEL"
        ]
        .map({
            "CRITICAL": 1,
            "LOW": 2,
        })
    )

    # CRITICAL -> LOW
    # 현재재고 적은 순
    # 같은 재고면 감소폭 큰 순
    low_stock_view = (
        filtered_low_stock_df
        .sort_values(
            [
                "위험도순",
                "STOCK",
                "STOCK_CHANGE",
            ],
            ascending=[
                True,
                True,
                True,
            ],
            na_position="last",
        )
        [
            [
                "LOW_STOCK_LEVEL",
                "IL_ITEM_ID",
                "ITEM_NAME",
                "MAIN_CATEGORY",
                "STOCK",
                "PREV_STOCK",
                "재고 증감",
                "ITEM_DUE_DATE",
            ]
        ]
        .rename(
            columns={
                "LOW_STOCK_LEVEL":
                    "위험도",

                "IL_ITEM_ID":
                    "상품ID",

                "ITEM_NAME":
                    "상품명",

                "MAIN_CATEGORY":
                    "카테고리",

                "STOCK":
                    "현재 재고",

                "PREV_STOCK":
                    "직전 재고",

                "ITEM_DUE_DATE":
                    "배송일",
            }
        )
    )

    st.dataframe(
        low_stock_view,
        use_container_width=True,
        hide_index=True,
        height=min(
            500,
            38
            * (
                len(
                    low_stock_view
                )
                + 1
            ),
        ),
    )


st.divider()


# ============================================================
# 오늘의 변화
# ============================================================

st.subheader(
    "🕒 오늘의 변화(품절 및 재입고)"
)


filtered_today_events = (
    apply_product_filter(
        today_events
    )
)


if filtered_today_events.empty:

    st.info(
        "검색 조건에 해당하는 "
        "오늘의 재고 이벤트가 없습니다."
    )

else:

    today_view = (
        filtered_today_events
        .sort_values(
            "EVENT_AT",
            ascending=False,
        )
        .copy()
    )

    today_view[
        "시간"
    ] = (
        today_view[
            "EVENT_AT"
        ]
        .dt.strftime(
            "%H:%M"
        )
    )

    today_view[
        "재고 변화"
    ] = (
        today_view[
            "PREV_STOCK"
        ]
        .apply(
            format_stock_value
        )
        + " → "
        + today_view[
            "CURRENT_STOCK"
        ]
        .apply(
            format_stock_value
        )
    )

    today_view = (
        today_view[
            [
                "EVENT_TYPE",
                "IL_ITEM_ID",
                "ITEM_NAME",
                "재고 변화",
                "시간",
                "CURRENT_DUE_DATE",
            ]
        ]
        .rename(
            columns={
                "EVENT_TYPE":
                    "이벤트",

                "IL_ITEM_ID":
                    "상품ID",

                "ITEM_NAME":
                    "상품명",

                "CURRENT_DUE_DATE":
                    "배송일",
            }
        )
    )

    st.dataframe(
        today_view,
        use_container_width=True,
        hide_index=True,
        height=350,
    )


st.divider()


# ============================================================
# 카테고리별 재고 현황
# ============================================================

st.subheader(
    "📊 카테고리별 재고 현황"
)


category_base = (
    active_df
    .groupby(
        "MAIN_CATEGORY",
        dropna=False,
    )
    .agg(
        상품수=(
            "IL_ITEM_ID",
            "count",
        ),

        품절수=(
            "STOCK",
            lambda x: (
                x == 0
            ).sum(),
        ),

        품절임박수=(
            "STOCK",
            lambda x: (
                (
                    x >= 1
                )
                &
                (
                    x <= 10
                )
            ).sum(),
        ),
    )
    .reset_index()
)


category_base[
    "품절률"
] = (
    category_base[
        "품절수"
    ]
    / category_base[
        "상품수"
    ]
    * 100
)


category_base = (
    category_base
    .sort_values(
        [
            "품절률",
            "품절수",
        ],
        ascending=False,
    )
)


category_view = (
    category_base
    .rename(
        columns={
            "MAIN_CATEGORY":
                "카테고리",
        }
    )
    .copy()
)


category_view[
    "품절률"
] = (
    category_view[
        "품절률"
    ]
    .map(
        lambda x:
        f"{x:.1f}%"
    )
)


cat_left, cat_right = (
    st.columns(
        [1.2, 1]
    )
)


with cat_left:

    st.dataframe(
        category_view,
        use_container_width=True,
        hide_index=True,
        height=400,
    )


with cat_right:

    chart_df = (
        category_base
        .set_index(
            "MAIN_CATEGORY"
        )
        [
            [
                "품절수",
                "품절임박수",
            ]
        ]
    )

    st.bar_chart(
        chart_df,
        use_container_width=True,
    )


# ============================================================
# Footer
# ============================================================

st.divider()

st.caption(
    "Greating Stock Monitor · "
    f"Dashboard v{VERSION}"
)