from app import (
    AppRequestHandler,
    BatchState,
    append_log_csv,
    batch_state,
    find_free_port,
    get_base_dir,
    get_web_dir,
    load_config,
    render_template,
    run_batch_dispatch,
    start_server,
    sync_config_to_env,
)

__all__ = [
    "AppRequestHandler",
    "BatchState",
    "append_log_csv",
    "batch_state",
    "find_free_port",
    "get_base_dir",
    "get_web_dir",
    "load_config",
    "render_template",
    "run_batch_dispatch",
    "start_server",
    "sync_config_to_env",
]

if __name__ == "__main__":
    start_server(port=None, open_browser=True)
