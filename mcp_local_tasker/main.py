import argparse

from .server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Local Task Tracker")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mode: stdio (for MCP clients), sse, or streamable-http (for HTTP)",
    )
    parser.add_argument(
        "--mount-path",
        default="/mcp",
        help="Mount path for SSE/streamable-http transport",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, mount_path=args.mount_path)


if __name__ == "__main__":
    main()
