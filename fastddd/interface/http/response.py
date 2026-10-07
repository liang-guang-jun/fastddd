"""Response code definitions for HTTP, WebSocket, and custom application errors."""

import dataclasses
from enum import Enum
from typing import Any, cast, overload

from fastapi import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class CustomCodeBase(Enum):
    """Base class for custom response and error codes."""

    @property
    def code(self) -> int:
        """Return the numeric response code."""
        code, _ = cast(tuple[int, str], self.value)
        return code

    @property
    def msg(self) -> str:
        """Return the response message."""
        _, msg = cast(tuple[int, str], self.value)
        return msg


class CustomResponseCode(CustomCodeBase):
    """Custom response status codes."""

    HTTP_200 = (200, "Success")
    HTTP_400 = (400, "Bad Request")
    HTTP_500 = (500, "Internal Server Error")


class CustomErrorCode(CustomCodeBase):
    """Custom application error codes."""

    CAPTCHA_ERROR = (40001, "Invalid CAPTCHA")


@dataclasses.dataclass
class CustomResponse:
    """Define a custom response code and message."""

    code: int
    msg: str


class StandardResponseCode:
    """Standard HTTP and WebSocket status codes."""

    # HTTP status codes
    # See:
    # https://www.iana.org/assignments/http-status-codes/http-status-codes.xhtml
    # https://datatracker.ietf.org/doc/html/rfc2324

    HTTP_100 = 100  # CONTINUE
    HTTP_101 = 101  # SWITCHING_PROTOCOLS
    HTTP_102 = 102  # PROCESSING
    HTTP_103 = 103  # EARLY_HINTS

    HTTP_200 = 200  # OK
    HTTP_201 = 201  # CREATED
    HTTP_202 = 202  # ACCEPTED
    HTTP_203 = 203  # NON_AUTHORITATIVE_INFORMATION
    HTTP_204 = 204  # NO_CONTENT
    HTTP_205 = 205  # RESET_CONTENT
    HTTP_206 = 206  # PARTIAL_CONTENT
    HTTP_207 = 207  # MULTI_STATUS
    HTTP_208 = 208  # ALREADY_REPORTED
    HTTP_226 = 226  # IM_USED

    HTTP_300 = 300  # MULTIPLE_CHOICES
    HTTP_301 = 301  # MOVED_PERMANENTLY
    HTTP_302 = 302  # FOUND
    HTTP_303 = 303  # SEE_OTHER
    HTTP_304 = 304  # NOT_MODIFIED
    HTTP_305 = 305  # USE_PROXY
    HTTP_307 = 307  # TEMPORARY_REDIRECT
    HTTP_308 = 308  # PERMANENT_REDIRECT

    HTTP_400 = 400  # BAD_REQUEST
    HTTP_401 = 401  # UNAUTHORIZED
    HTTP_402 = 402  # PAYMENT_REQUIRED
    HTTP_403 = 403  # FORBIDDEN
    HTTP_404 = 404  # NOT_FOUND
    HTTP_405 = 405  # METHOD_NOT_ALLOWED
    HTTP_406 = 406  # NOT_ACCEPTABLE
    HTTP_407 = 407  # PROXY_AUTHENTICATION_REQUIRED
    HTTP_408 = 408  # REQUEST_TIMEOUT
    HTTP_409 = 409  # CONFLICT
    HTTP_410 = 410  # GONE
    HTTP_411 = 411  # LENGTH_REQUIRED
    HTTP_412 = 412  # PRECONDITION_FAILED
    HTTP_413 = 413  # CONTENT_TOO_LARGE
    HTTP_414 = 414  # URI_TOO_LONG
    HTTP_415 = 415  # UNSUPPORTED_MEDIA_TYPE
    HTTP_416 = 416  # RANGE_NOT_SATISFIABLE
    HTTP_417 = 417  # EXPECTATION_FAILED
    HTTP_418 = 418  # IM_A_TEAPOT
    HTTP_421 = 421  # MISDIRECTED_REQUEST
    HTTP_422 = 422  # UNPROCESSABLE_CONTENT
    HTTP_423 = 423  # LOCKED
    HTTP_424 = 424  # FAILED_DEPENDENCY
    HTTP_425 = 425  # TOO_EARLY
    HTTP_426 = 426  # UPGRADE_REQUIRED
    HTTP_427 = 427  # UNASSIGNED
    HTTP_428 = 428  # PRECONDITION_REQUIRED
    HTTP_429 = 429  # TOO_MANY_REQUESTS
    HTTP_430 = 430  # UNASSIGNED
    HTTP_431 = 431  # REQUEST_HEADER_FIELDS_TOO_LARGE
    HTTP_451 = 451  # UNAVAILABLE_FOR_LEGAL_REASONS

    HTTP_500 = 500  # INTERNAL_SERVER_ERROR
    HTTP_501 = 501  # NOT_IMPLEMENTED
    HTTP_502 = 502  # BAD_GATEWAY
    HTTP_503 = 503  # SERVICE_UNAVAILABLE
    HTTP_504 = 504  # GATEWAY_TIMEOUT
    HTTP_505 = 505  # HTTP_VERSION_NOT_SUPPORTED
    HTTP_506 = 506  # VARIANT_ALSO_NEGOTIATES
    HTTP_507 = 507  # INSUFFICIENT_STORAGE
    HTTP_508 = 508  # LOOP_DETECTED
    HTTP_509 = 509  # UNASSIGNED
    HTTP_510 = 510  # NOT_EXTENDED
    HTTP_511 = 511  # NETWORK_AUTHENTICATION_REQUIRED

    # WebSocket close codes
    # See:
    # https://www.iana.org/assignments/websocket/websocket.xml#close-code-number
    # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent

    WS_1000 = 1000  # NORMAL_CLOSURE
    WS_1001 = 1001  # GOING_AWAY
    WS_1002 = 1002  # PROTOCOL_ERROR
    WS_1003 = 1003  # UNSUPPORTED_DATA
    WS_1005 = 1005  # NO_STATUS_RCVD
    WS_1006 = 1006  # ABNORMAL_CLOSURE
    WS_1007 = 1007  # INVALID_FRAME_PAYLOAD_DATA
    WS_1008 = 1008  # POLICY_VIOLATION
    WS_1009 = 1009  # MESSAGE_TOO_BIG
    WS_1010 = 1010  # MANDATORY_EXTENSION
    WS_1011 = 1011  # INTERNAL_ERROR
    WS_1012 = 1012  # SERVICE_RESTART
    WS_1013 = 1013  # TRY_AGAIN_LATER
    WS_1014 = 1014  # BAD_GATEWAY
    WS_1015 = 1015  # TLS_HANDSHAKE

    WS_3000 = 3000  # UNAUTHORIZED
    WS_3003 = 3003  # FORBIDDEN


class ResponseModel(BaseModel):
    """Generic API response model without a typed data schema.

    Examples:
        Use as a FastAPI response model:

            @router.get("/test", response_model=ResponseModel)
            def test():
                return ResponseModel(data={"test": "test"})

        Use as a return annotation:

            @router.get("/test")
            def test() -> ResponseModel:
                return ResponseModel(data={"test": "test"})

        Use with a custom response code:

            @router.get("/test")
            def test() -> ResponseModel:
                res = CustomResponseCode.HTTP_200
                return ResponseModel(
                    code=res.code,
                    msg=res.msg,
                    data={"test": "test"},
                )
    """

    code: int = Field(
        default=CustomResponseCode.HTTP_200.code,
        description="Response code",
    )
    msg: str = Field(
        default=CustomResponseCode.HTTP_200.msg,
        description="Response message",
    )
    data: Any | None = Field(
        default=None,
        description="Response data",
    )


class ResponseSchemaModel[SchemaT](ResponseModel):
    """Generic API response model with a typed data schema.

    Examples:
        Use as a FastAPI response model:

            @router.get(
                "/test",
                response_model=ResponseSchemaModel[GetApiDetail],
            )
            def test():
                return ResponseSchemaModel[GetApiDetail](
                    data=GetApiDetail(...),
                )

        Use as a return annotation:

            @router.get("/test")
            def test() -> ResponseSchemaModel[GetApiDetail]:
                return ResponseSchemaModel[GetApiDetail](
                    data=GetApiDetail(...),
                )

        Use with a custom response code:

            @router.get("/test")
            def test() -> ResponseSchemaModel[GetApiDetail]:
                res = CustomResponseCode.HTTP_200
                return ResponseSchemaModel[GetApiDetail](
                    code=res.code,
                    msg=res.msg,
                    data=GetApiDetail(...),
                )
    """

    data: SchemaT


class ResponseBase:
    """Provide helpers for building standardized API responses."""

    @staticmethod
    def __response(
        *,
        res: CustomResponseCode | CustomResponse,
        data: Any | None,
    ) -> ResponseModel | ResponseSchemaModel[Any]:
        """Build a standardized API response.

        Args:
            res: Response code and message definition.
            data: Optional response payload.

        Returns:
            A response model containing response metadata and payload.
        """
        if data is None:
            return ResponseModel(
                code=res.code,
                msg=res.msg,
                data=None,
            )

        return ResponseSchemaModel[Any](
            code=res.code,
            msg=res.msg,
            data=data,
        )

    @overload
    def success(
        self,
        *,
        res: CustomResponseCode | CustomResponse = CustomResponseCode.HTTP_200,
        data: None = None,
    ) -> ResponseModel: ...

    @overload
    def success[SchemaT](
        self,
        *,
        res: CustomResponseCode | CustomResponse = CustomResponseCode.HTTP_200,
        data: SchemaT,
    ) -> ResponseSchemaModel[SchemaT]: ...

    def success(
        self,
        *,
        res: CustomResponseCode | CustomResponse = CustomResponseCode.HTTP_200,
        data: Any | None = None,
    ) -> ResponseModel | ResponseSchemaModel[Any]:
        """Build a successful API response.

        Args:
            res: Response code and message definition.
            data: Optional response payload.

        Returns:
            A standardized success response.
        """
        return self.__response(res=res, data=data)

    @overload
    def fail(
        self,
        *,
        res: CustomResponseCode | CustomResponse = CustomResponseCode.HTTP_400,
        data: None = None,
    ) -> ResponseModel: ...

    @overload
    def fail[SchemaT](
        self,
        *,
        res: CustomResponseCode | CustomResponse = CustomResponseCode.HTTP_400,
        data: SchemaT,
    ) -> ResponseSchemaModel[SchemaT]: ...

    def fail(
        self,
        *,
        res: CustomResponseCode | CustomResponse = CustomResponseCode.HTTP_400,
        data: Any | None = None,
    ) -> ResponseModel | ResponseSchemaModel[Any]:
        """Build a failed API response.

        Args:
            res: Response code and message definition.
            data: Optional response payload.

        Returns:
            A standardized failure response.
        """
        return self.__response(res=res, data=data)

    @staticmethod
    def fast_success(
        *,
        res: CustomResponseCode | CustomResponse = CustomResponseCode.HTTP_200,
        data: Any | None = None,
    ) -> Response:
        """Build a JSON response without Pydantic response-model validation.

        This method returns a JSON response directly and bypasses FastAPI's
        response-model validation. It is useful when the payload is already
        validated and JSON-compatible.

        Do not specify a FastAPI ``response_model`` when using this method as
        the direct return value.

        Args:
            res: Response code and message definition.
            data: Optional JSON-compatible response payload.

        Returns:
            A JSON response containing the standardized response structure.
        """
        return JSONResponse(
            content={
                "code": res.code,
                "msg": res.msg,
                "data": data,
            }
        )


response_base = ResponseBase()
