from flask import Flask, jsonify, request
import os
from datetime import datetime
import mysql.connector

mysql_connector = mysql.connector


def env_or_fallback(primary_name, fallback_name=None):
    value = os.getenv(primary_name)
    if value:
        return value
    if fallback_name:
        return os.getenv(fallback_name)
    return None


MYSQL_HOST = env_or_fallback("AZURE_MYSQL_HOST", "MYSQLCONNSTR_AZURE_MYSQL_HOST")
MYSQL_USER = env_or_fallback("AZURE_MYSQL_USER", "MYSQLCONNSTR_AZURE_MYSQL_USER")
MYSQL_PASSWORD = env_or_fallback("AZURE_MYSQL_PASSWORD", "MYSQLCONNSTR_AZURE_MYSQL_PASSWORD")
MYSQL_DATABASE = env_or_fallback("AZURE_DATABASE_NAME", "MYSQLCONNSTR_AZURE_DATABASE_NAME")
MYSQL_PORT = int(env_or_fallback("AZURE_MYSQL_PORT", "MYSQLCONNSTR_AZURE_MYSQL_PORT") or "3306")
VALID_API_KEYS = {
    key.strip() for key in os.getenv("AZURE_API_KEYS", "").split(",") if key.strip()
}

app = Flask(__name__)
app.config['START_TIME'] = datetime.now()




#All endpoints except /api/v1/health require a valid API key passed in the request header. 
# Keys are stored in Azure App Service environment variables and never hard-coded in scripts.

def validate_api_key():
    api_key = request.headers.get('X-API-Key')
    return bool(api_key) and api_key in VALID_API_KEYS


def get_mysql_connection():
    if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
        missing = [name for name, value in {
            "AZURE_MYSQL_HOST": MYSQL_HOST,
            "AZURE_MYSQL_USER": MYSQL_USER,
            "AZURE_MYSQL_PASSWORD": MYSQL_PASSWORD,
            "AZURE_DATABASE_NAME": MYSQL_DATABASE,
        }.items() if not value]
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )


@app.route('/api/v1/metrics', methods=['POST'])
def add_metric():
    if not validate_api_key():
        return jsonify({"error": "Invalid or missing API key"}), 401

    if mysql_connector is None:
        return jsonify({"error": "mysql-connector-python is not installed"}), 500

    data = request.get_json()
    host = data.get('host')
    cpu_usage = data.get('cpu_usage')
    memory_usage = data.get('memory_usage')

    try:
        with get_mysql_connection() as connection:
            cursor = connection.cursor()
            query = "INSERT INTO metrics (host, cpu_usage, memory_usage) VALUES (%s, %s, %s)"
            cursor.execute(query, (host, cpu_usage, memory_usage))
            connection.commit()
            return jsonify({"message": "Metric added successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


@app.route('/api/v1/metrics', methods=['GET'])
def get_metrics():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    host = request.args.get('host')
    if not validate_api_key():
        return jsonify({"error": "Invalid or missing API key"}), 401

    if mysql_connector is None:
        return jsonify({"error": "mysql-connector-python is not installed"}), 500

    try:
        with get_mysql_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            query = "SELECT * FROM metrics WHERE timestamp BETWEEN %s AND %s"
            params = (start_date, end_date)

            if host:
                query += " AND host = %s"
                params += (host,)

            cursor.execute(query, params)
            results = cursor.fetchall()
            return jsonify(results), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/health', methods=['GET'])
def health_check():
    start_time = app.config.get('START_TIME')
    uptime_seconds = int((datetime.now() - start_time).total_seconds()) if start_time else 0
    test_db_connection = False

    if mysql_connector is None:
        return jsonify({
            "status": "degraded",
            "uptime_seconds": uptime_seconds,
            "db_connection": False,
            "error": "mysql-connector-python is not installed"
        }), 200

    try:
        with get_mysql_connection() as connection:
            test_db_connection = True
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "uptime_seconds": uptime_seconds,
            "db_connection": False,
            "error": str(e)
        }), 500

    return jsonify({
        "status": "healthy",
        "uptime_seconds": uptime_seconds,
        "db_connection": test_db_connection
    }), 200


if __name__ == '__main__':
    # Run locally when launched with: python api.py
    app.run(host='0.0.0.0', port=5000, debug=True)
