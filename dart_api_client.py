import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests


@dataclass
class Disclosure:
    """DART OpenAPI에서 조회된 개별 공시 정보"""

    corp_code: str
    corp_name: str
    stock_code: str
    corp_cls: str
    report_nm: str
    rcept_no: str
    flr_nm: str
    rcept_dt: str
    rm: str

    @classmethod
    def from_dict(cls, data: dict) -> "Disclosure":
        return cls(
            corp_code=data.get("corp_code", ""),
            corp_name=data.get("corp_name", ""),
            stock_code=data.get("stock_code", ""),
            corp_cls=data.get("corp_cls", ""),
            report_nm=data.get("report_nm", ""),
            rcept_no=data.get("rcept_no", ""),
            flr_nm=data.get("flr_nm", ""),
            rcept_dt=data.get("rcept_dt", ""),
            rm=data.get("rm", ""),
        )

    @property
    def dart_url(self) -> str:
        """DART 공시 상세 페이지 URL"""
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"

    def __str__(self) -> str:
        return f"[{self.rcept_dt}] {self.corp_name} ({self.stock_code}) - {self.report_nm}"

    def to_dict(self) -> dict:
        return {
            "corp_code": self.corp_code,
            "corp_name": self.corp_name,
            "stock_code": self.stock_code,
            "corp_cls": self.corp_cls,
            "report_nm": self.report_nm,
            "rcept_no": self.rcept_no,
            "flr_nm": self.flr_nm,
            "rcept_dt": self.rcept_dt,
            "rm": self.rm,
        }


@dataclass
class CorpInfo:
    """corp_code와 stock_code의 매핑 정보"""

    corp_code: str
    corp_name: str
    stock_code: str


class DartApiClient:
    """DART OpenAPI 클라이언트"""

    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = requests.Session()
        # stock_code → CorpInfo 매핑
        self._stock_to_corp: dict[str, CorpInfo] = {}
        # corp_code → CorpInfo 매핑
        self._corp_code_map: dict[str, CorpInfo] = {}

    def initialize(self) -> None:
        """기업 고유번호 데이터를 초기화합니다.

        DART API에서 corpCode.xml을 다운로드하여
        종목코드 ↔ 기업고유번호 매핑 테이블을 구축합니다.
        """
        print("📥 DART 기업 고유번호 데이터를 다운로드 중...")

        url = f"{self.BASE_URL}/corpCode.xml"
        resp = self._session.get(url, params={"crtfc_key": self.api_key})
        resp.raise_for_status()

        # ZIP 파일 해제 → XML 파싱
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_name = [n for n in zf.namelist() if n.endswith(".xml")][0]
            xml_bytes = zf.read(xml_name)

        root = ET.fromstring(xml_bytes)
        mapped_count = 0

        for elem in root.iter("list"):
            corp_code = (elem.findtext("corp_code") or "").strip()
            corp_name = (elem.findtext("corp_name") or "").strip()
            stock_code = (elem.findtext("stock_code") or "").strip()

            if not corp_code:
                continue

            info = CorpInfo(corp_code=corp_code, corp_name=corp_name, stock_code=stock_code)
            self._corp_code_map[corp_code] = info

            if stock_code:
                self._stock_to_corp[stock_code] = info
                mapped_count += 1

        print(
            f"✅ 기업 고유번호 로드 완료: "
            f"총 {len(self._corp_code_map)}개 기업, {mapped_count}개 상장사 매핑"
        )

    def get_corp_code(self, stock_code: str) -> str | None:
        """종목코드로 기업 고유번호를 조회합니다."""
        info = self._stock_to_corp.get(stock_code)
        return info.corp_code if info else None

    def get_corp_info(self, corp_code: str) -> CorpInfo | None:
        """기업 고유번호로 기업 정보를 조회합니다."""
        return self._corp_code_map.get(corp_code)

    def get_corp_codes_for_stocks(self, stock_codes: list[str]) -> set[str]:
        """종목코드 리스트에 해당하는 corp_code 세트를 반환합니다."""
        corp_codes: set[str] = set()
        for sc in stock_codes:
            cc = self.get_corp_code(sc)
            if cc:
                corp_codes.add(cc)
        return corp_codes

    def fetch_disclosures(
        self,
        begin_date: str,
        end_date: str,
        pblntf_ty: str | None = None,
        page_no: int = 1,
        page_count: int = 100,
    ) -> list[Disclosure]:
        """DART 공시 목록을 조회합니다.

        Args:
            begin_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
            pblntf_ty: 공시유형 (B: 주요사항보고)
            page_no: 페이지 번호
            page_count: 페이지당 건수
        """
        params: dict[str, str | int] = {
            "crtfc_key": self.api_key,
            "bgn_de": begin_date,
            "end_de": end_date,
            "page_no": page_no,
            "page_count": page_count,
        }
        if pblntf_ty:
            params["pblntf_ty"] = pblntf_ty

        resp = self._session.get(f"{self.BASE_URL}/list.json", params=params)
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status")
        if status == "013":
            return []
        if status != "000":
            msg = data.get("message", "알 수 없는 오류")
            raise RuntimeError(f"DART API 오류 ({status}): {msg}")

        return [Disclosure.from_dict(item) for item in data.get("list", [])]

    def fetch_all_disclosures(
        self,
        begin_date: str,
        end_date: str,
        pblntf_ty: str | None = None,
    ) -> list[Disclosure]:
        """모든 페이지의 공시를 조회합니다."""
        import time

        all_disclosures: list[Disclosure] = []
        page_no = 1
        page_count = 100

        while True:
            disclosures = self.fetch_disclosures(
                begin_date=begin_date,
                end_date=end_date,
                pblntf_ty=pblntf_ty,
                page_no=page_no,
                page_count=page_count,
            )
            all_disclosures.extend(disclosures)

            if len(disclosures) < page_count:
                break

            page_no += 1
            time.sleep(0.1)  # Rate limiting

        return all_disclosures

    def close(self) -> None:
        """HTTP 세션을 닫습니다."""
        self._session.close()
