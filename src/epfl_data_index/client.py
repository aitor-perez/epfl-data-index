from opensearchpy import OpenSearch

from epfl_data_index.config import CONFIG


def get_client():
    return OpenSearch(
        hosts=[{"host": CONFIG["EDI_OPENSEARCH_HOST"], "port": CONFIG["EDI_OPENSEARCH_PORT"]}],
        http_auth=(CONFIG["EDI_OPENSEARCH_USER"], CONFIG["EDI_OPENSEARCH_PASSWORD"]),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False,
    )
