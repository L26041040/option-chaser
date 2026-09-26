"""SECURITY-FIX-01：`POST /api/analyze` 公開端點已退休。引擎契約測試改走
`create_app()` 留下的**內部** seam（`app.state.analyze_request`，沒有任何
HTTP 路由），這裡把它包成跟原本 `client.post("/api/analyze", ...)` 差不多
的形狀（`status_code`／`json()`），讓既有測試只換一行呼叫方式。

- 成功：`status_code == 200`，`json()` 是引擎 view（經 FastAPI 同一道
  `jsonable_encoder`，跟原本 HTTP 回應逐位元相同）。
- `_analyze()` 丟的分層失敗（`HTTPException`，stage／message）：原樣帶出
  狀態碼與 `{"detail": ...}`——跟 scenario refresh 共用同一套分類。
- 參數驗證失敗（pydantic）：422，跟原本 FastAPI 的行為一致。

用 cookie identity 的 app（沒有 DI 覆寫身份）在 request 之外沒有 owner，
這裡用一個固定的測試 owner scope 包起來。
"""
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from api_app.identity import resolved_owner_scope


class AdhocResult:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def post_adhoc(client, body: dict) -> AdhocResult:
    with resolved_owner_scope("adhoc-test-owner"):
        try:
            # 跟原本 HTTP 回應走同一道序列化（tuple→list 等），比對契約樣本
            # 才是在比「前端真正會收到的東西」。
            view = client.app.state.analyze_request(body)
            return AdhocResult(200, jsonable_encoder(view))
        except HTTPException as e:
            return AdhocResult(e.status_code, {"detail": e.detail})
        except ValidationError as e:
            return AdhocResult(422, {"detail": e.errors()})
