"""
models.py
Pydantic v2 資料模型

用途：
- 嚴格驗證輸入（email 格式、必填欄位、JSON 結構）
- 統一序列化/反序列化（給 Supabase 與 Streamlit 表單）
- 提供 from_db / to_db 輔助方法，處理 JSONB 與 datetime

注意：
- Supabase 回傳的 timestamp 為 ISO 字串，我們轉成 datetime 物件
- products 永遠是 list[str]
- api_kit 與 request_history 使用巢狀模型或 dict 彈性處理
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------- 子模型 ----------

class ApiKit(BaseModel):
    """客戶目前的 API Kit 需求狀態"""
    json: bool = False
    api_pdf: bool = False
    product_specs: bool = False
    last_requested: datetime | None = None

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        }
    )

    @field_validator("last_requested", mode="before")
    @classmethod
    def parse_last_requested(cls, v: Any) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # 支援帶 Z 或不帶的 ISO 格式
            try:
                if v.endswith("Z"):
                    v = v[:-1] + "+00:00"
                return datetime.fromisoformat(v)
            except Exception:
                return None
        return None


class RequestRecord(BaseModel):
    """單筆請求歷史紀錄（存在 request_history JSONB array 中）"""
    timestamp: str = Field(..., description="ISO 格式時間字串，建議 UTC")
    template_used: str = ""
    products: list[str] = Field(default_factory=list)
    api_type: Literal["json", "api_pdf", "product_specs", "mixed"] = "json"
    notes: str = ""

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_timestamp(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc).isoformat()
        if isinstance(v, str):
            return v
        return datetime.now(timezone.utc).isoformat()

    @field_validator("products", mode="before")
    @classmethod
    def normalize_products(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, list):
            return [str(p).strip() for p in v if str(p).strip()]
        return []


class ClientProfile(BaseModel):
    """完整客戶檔案模型（對應 client_profiles 表）"""

    id: str | None = None
    name: str = Field(..., min_length=1, description="客戶名稱")
    email: str = Field(..., min_length=3, description="唯一識別用 email")
    country: str | None = None
    from_where: str | None = None

    # JSONB 欄位
    api_kit: ApiKit | dict[str, Any] = Field(default_factory=dict)
    products: list[str] = Field(default_factory=list)
    customer_cluster: str | None = None
    request_history: list[RequestRecord] | list[dict[str, Any]] = Field(default_factory=list)

    last_edited: datetime | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        },
        arbitrary_types_allowed=True,
    )

    # ---------- 驗證器 ----------

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if v is None:
            return ""
        return str(v).strip().lower()

    @field_validator("products", mode="before")
    @classmethod
    def normalize_products(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, list):
            return [str(p).strip() for p in v if str(p).strip()]
        return []

    @field_validator("api_kit", mode="before")
    @classmethod
    def normalize_api_kit(cls, v: Any) -> ApiKit | dict[str, Any]:
        if v is None:
            return {}
        if isinstance(v, ApiKit):
            return v
        if isinstance(v, dict):
            # 允許直接傳 dict，之後可再轉 ApiKit
            return v
        return {}

    @field_validator("request_history", mode="before")
    @classmethod
    def normalize_history(cls, v: Any) -> list:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return []

    @model_validator(mode="after")
    def ensure_api_kit_object(self) -> ClientProfile:
        """確保 api_kit 盡量是 ApiKit 物件（方便後續使用 .json 等屬性）"""
        if isinstance(self.api_kit, dict):
            try:
                self.api_kit = ApiKit.model_validate(self.api_kit)
            except Exception:
                # 保留原始 dict，讓上層決定如何處理
                pass
        return self

    # ---------- 序列化輔助 ----------

    def to_db_dict(self) -> dict[str, Any]:
        """
        轉成適合直接傳給 Supabase 的 dict（JSONB 會自動序列化）
        """
        data = self.model_dump(mode="json", exclude_none=True)

        # 確保 api_kit 是純 dict
        if isinstance(self.api_kit, ApiKit):
            data["api_kit"] = self.api_kit.model_dump(mode="json")
        elif isinstance(self.api_kit, dict):
            data["api_kit"] = self.api_kit

        # 確保 products 是 list
        data["products"] = self.products or []

        # request_history 轉成 list of dict
        history: list[dict] = []
        for item in self.request_history or []:
            if isinstance(item, RequestRecord):
                history.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                history.append(item)
        data["request_history"] = history

        # last_edited 由資料庫或呼叫端負責填入
        data.pop("id", None)  # insert 時通常不要手動給 id
        return data

    @classmethod
    def from_db(cls, row: dict[str, Any]) -> ClientProfile:
        """
        從 Supabase 回傳的 row 建立模型（處理 datetime 與 JSONB）
        """
        if not row:
            raise ValueError("row 不可為空")

        # 複製避免修改原始資料
        data = dict(row)

        # 轉 api_kit
        if isinstance(data.get("api_kit"), dict):
            try:
                data["api_kit"] = ApiKit.model_validate(data["api_kit"])
            except Exception:
                pass

        # 轉 request_history 為模型列表（盡量）
        raw_history = data.get("request_history") or []
        parsed_history: list = []
        for h in raw_history:
            try:
                if isinstance(h, dict):
                    parsed_history.append(RequestRecord.model_validate(h))
                else:
                    parsed_history.append(h)
            except Exception:
                parsed_history.append(h)
        data["request_history"] = parsed_history

        # 轉 last_edited
        if isinstance(data.get("last_edited"), str):
            try:
                ts = data["last_edited"]
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                data["last_edited"] = datetime.fromisoformat(ts)
            except Exception:
                data["last_edited"] = None

        return cls.model_validate(data)

    def __repr__(self) -> str:
        return f"<ClientProfile email={self.email} name={self.name} cluster={self.customer_cluster}>"
