from openhasp_config_manager.cli import cli

if __name__ == "__main__":
    import os
    import sys

    parent_dir = os.path.abspath(os.path.join(os.path.abspath(__file__), "..", ".."))
    sys.path.append(parent_dir)

if __name__ == '__main__':
    cli()
