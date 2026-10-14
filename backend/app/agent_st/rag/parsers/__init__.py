from app.agent_st.rag.parsers.pdf import PdfParser
from app.agent_st.rag.parsers.ppt import PptParser
from app.agent_st.rag.parsers.txt import TxtParser

# 题库不再从 JSON 文件入库（改为主库 questions 表，见 ingest.ingest_question_bank），
# 因此这里不再注册 JsonBankParser。
PARSERS = (PdfParser(), PptParser(), TxtParser())


def get_parser(path):
    for parser in PARSERS:
        if parser.can_parse(path):
            return parser
    raise ValueError(f"没有可用解析器：{path}")
