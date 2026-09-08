from app.agent_st.rag.parsers.json_bank import JsonBankParser
from app.agent_st.rag.parsers.pdf import PdfParser
from app.agent_st.rag.parsers.ppt import PptParser
from app.agent_st.rag.parsers.txt import TxtParser

PARSERS = (JsonBankParser(), PdfParser(), PptParser(), TxtParser())


def get_parser(path):
    for parser in PARSERS:
        if parser.can_parse(path):
            return parser
    raise ValueError(f"没有可用解析器：{path}")
