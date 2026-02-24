import sys
from unittest.mock import patch


def test_main_stdio_transport():
    import mcp_local_tasker.main as main_module

    with patch.object(main_module.mcp, "run") as mock_run:
        with patch.object(sys, "argv", ["mcp_local_tasker", "--transport", "stdio"]):
            main_module.main()
        mock_run.assert_called_once_with(transport="stdio")


def test_main_sse_transport():
    import mcp_local_tasker.main as main_module

    with patch.object(main_module.mcp, "run") as mock_run:
        with patch.object(sys, "argv", ["mcp_local_tasker", "--transport", "sse"]):
            main_module.main()
        mock_run.assert_called_once_with(transport="sse", mount_path="/mcp")


def test_main_streamable_http():
    import mcp_local_tasker.main as main_module

    with patch.object(main_module.mcp, "run") as mock_run:
        with patch.object(
            sys, "argv", ["mcp_local_tasker", "--transport", "streamable-http"]
        ):
            main_module.main()
        mock_run.assert_called_once_with(transport="streamable-http", mount_path="/mcp")


def test_main_custom_mount():
    import mcp_local_tasker.main as main_module

    with patch.object(main_module.mcp, "run") as mock_run:
        with patch.object(
            sys,
            "argv",
            ["mcp_local_tasker", "--transport", "sse", "--mount-path", "/custom"],
        ):
            main_module.main()
        mock_run.assert_called_once_with(transport="sse", mount_path="/custom")


def test_main_default():
    import mcp_local_tasker.main as main_module

    with patch.object(main_module.mcp, "run") as mock_run:
        with patch.object(sys, "argv", ["mcp_local_tasker"]):
            main_module.main()
        mock_run.assert_called_once_with(transport="stdio")
