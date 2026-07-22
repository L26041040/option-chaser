FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY option_chaser ./option_chaser
COPY webapp ./webapp
COPY .streamlit ./.streamlit
RUN pip install --no-cache-dir ".[gui]"
ENV PORT=8501
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD \
  python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8501')+'/_stcore/health')"
CMD ["sh", "-c", "streamlit run webapp/app.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true"]
