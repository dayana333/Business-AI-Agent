from . import kaspi_search, market_data

TOOLS = {
    market_data.TOOL_SPEC["function"]["name"]: market_data,
    kaspi_search.TOOL_SPEC["function"]["name"]: kaspi_search,
}
