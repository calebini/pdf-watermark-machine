"""PyInstaller entry point; keep imports absolute for frozen execution."""
from pdf_watermark.cli import main

raise SystemExit(main())
