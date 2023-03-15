from openhasp_config_manager.cli import cli


def main():
    import os
    import sys

    parent_dir = os.path.abspath(os.path.join(os.path.abspath(__file__), "..", ".."))
    sys.path.append(parent_dir)

    cli()


if __name__ == '__main__':
    main()
