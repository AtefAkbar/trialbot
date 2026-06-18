# Container for the Polymarket copy-trader (PAPER). Runs engine + dashboard.
# Works on Fly.io, Render, Railway, or any container host.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY copytrader ./copytrader

ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "copytrader.serve"]
