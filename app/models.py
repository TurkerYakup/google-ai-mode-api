from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

Device = Literal["desktop", "mobile"]
TaskStatus = Literal["queued", "running", "done", "error"]


class QueryOptions(BaseModel):
    """Tum uclarda ortak istege bagli parametreler.

    DataForSEO'dan gecis kolay olsun diye bazi alanlar ayni anda iki isimle kabul edilir
    (or. hl / language_code, location / location_name).
    """

    model_config = ConfigDict(populate_by_name=True)

    hl: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("hl", "language_code"),
        description="Arayuz dili: 'tr', 'en', 'de' ... (alias: language_code)",
    )
    gl: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("gl", "country_code"),
        description="Ulke kodu: 'TR', 'US', 'DE' ... (alias: country_code)",
    )
    google_domain: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("google_domain", "se_domain"),
        description="Arama motoru alan adi, or. 'www.google.com.tr' (alias: se_domain)",
    )
    location: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("location", "location_name"),
        description="Konum hedefi, Google kanonik adi. Or. 'Istanbul,Turkey' veya "
        "'New York,New York,United States'. uule parametresine cevrilir. (alias: location_name)",
        examples=["Istanbul,Turkey"],
    )
    uule: Optional[str] = Field(None, description="Hazir uule degeri. Verilirse 'location' yok sayilir.")
    device: Device = Field("desktop", description="Hangi cihaz profiliyle sorulacak")

    track_domains: List[str] = Field(
        default_factory=list,
        description="Bu domainler atif listesinde var mi diye kontrol edilir (alt alan adlari dahil)",
        examples=[["ornek.com", "rakip.com"]],
    )
    track_brands: List[str] = Field(
        default_factory=list,
        description="Bu ifadeler cevap metninde geciyor mu diye aranir (buyuk/kucuk harf duyarsiz)",
        examples=[["Marka Adi"]],
    )

    include_blocks: bool = Field(True, description="Cevabi yapisal bloklara ayrilmis halde de dondur")
    include_html: bool = Field(False, description="Cevap kapsayicisinin ham HTML'ini dondur")
    include_screenshot: bool = Field(False, description="Sayfanin PNG ekran goruntusunu base64 dondur")
    include_follow_ups: bool = Field(True, description="Google'in onerdigi devam sorularini dondur")

    timeout: Optional[float] = Field(None, ge=5, le=300, description="Cevap icin ust sinir (saniye)")
    cache: bool = Field(True, description="Ayni sorgu icin onbellek kullan (TTL sunucu ayari)")


class QueryRequest(QueryOptions):
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        validation_alias=AliasChoices("query", "keyword", "q"),
        description="AI Mode'a sorulacak soru (alias: keyword, q)",
    )


class BatchRequest(QueryOptions):
    queries: List[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        validation_alias=AliasChoices("queries", "keywords"),
        description="Sirayla sorulacak keyword listesi (alias: keywords)",
    )
    stop_on_error: bool = Field(False, description="Ilk hatada duralim mi")


class TaskRequest(QueryRequest):
    postback_url: Optional[str] = Field(
        None,
        description="Gorev bitince sonucun POST edilecegi URL (DataForSEO'daki postback_url gibi)",
    )
    tag: Optional[str] = Field(None, max_length=200, description="Kendi takip etiketiniz, sonucta aynen doner")


class BatchTaskRequest(BatchRequest):
    postback_url: Optional[str] = None
    tag: Optional[str] = Field(None, max_length=200)


# --- sonuc parcalari -------------------------------------------------------


class Link(BaseModel):
    title: str
    url: str
    domain: str


class Citation(Link):
    position: int = Field(..., description="Cevap icinde gorunme sirasi, 1'den baslar")


class Block(BaseModel):
    """Cevabin bir parcasi. Hangi iddianin hangi kaynagi gosterdigini eslestirmek icin."""

    type: Literal["heading", "paragraph", "list", "table", "code"]
    text: Optional[str] = None
    level: Optional[int] = None
    ordered: Optional[bool] = None
    items: Optional[List[Dict[str, Any]]] = None
    rows: Optional[List[List[str]]] = None
    links: List[Link] = []


class DomainStat(BaseModel):
    domain: str
    citations: int = Field(..., description="Bu domainden kac farkli link atif almis")
    first_position: int
    share: float = Field(..., description="Tum atiflar icindeki pay, 0-1 arasi")
    urls: List[str]


class DomainMatch(BaseModel):
    domain: str
    cited: bool
    positions: List[int] = []
    urls: List[str] = []


class BrandMatch(BaseModel):
    brand: str
    mentioned: bool
    count: int = 0
    contexts: List[str] = Field(default_factory=list, description="Gectigi yerlerden kisa alintilar")


class AnswerStats(BaseModel):
    characters: int
    words: int
    citation_count: int
    unique_domains: int
    block_count: int


class QueryResult(BaseModel):
    status: Literal["ok"] = "ok"
    query: str
    answer: str = Field(..., description="AI Mode cevabi, markdown")
    blocks: Optional[List[Block]] = None
    citations: List[Citation] = []
    domains: List[DomainStat] = Field(default_factory=list, description="Domain bazinda atif ozeti")
    follow_ups: List[str] = []
    tracked_domains: List[DomainMatch] = []
    tracked_brands: List[BrandMatch] = []
    stats: AnswerStats
    source_url: str
    device: Device = "desktop"
    hl: Optional[str] = None
    gl: Optional[str] = None
    resolved_location: Optional[str] = None
    cached: bool = False
    truncated: bool = Field(False, description="Akis bitmeden zaman asimina ugradi")
    elapsed_ms: int
    extracted_by: Optional[str] = Field(None, description="Hangi selector/heuristik ile bulundu (hata ayiklama)")
    html: Optional[str] = None
    screenshot_base64: Optional[str] = None


class BatchItem(BaseModel):
    query: str
    result: Optional[QueryResult] = None
    error: Optional[Dict[str, str]] = None


class BatchResponse(BaseModel):
    status: Literal["ok"] = "ok"
    count: int
    succeeded: int
    failed: int
    elapsed_ms: int
    items: List[BatchItem]


# --- async gorevler --------------------------------------------------------


class TaskCreated(BaseModel):
    task_id: str
    status: TaskStatus = "queued"
    tag: Optional[str] = None
    created_at: str
    poll_url: str


class TaskInfo(BaseModel):
    task_id: str
    status: TaskStatus
    kind: Literal["query", "batch"]
    tag: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    progress: Optional[str] = Field(None, description="Toplu gorevlerde '3/10' gibi ilerleme")
    result: Optional[Any] = None
    error: Optional[Dict[str, str]] = None


class TaskList(BaseModel):
    count: int
    tasks: List[TaskInfo]


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    code: str
    message: str
    detail: Optional[str] = None
