"""Optional: the same daily job as an Airflow DAG (drop into your dags/ folder).
Set PROJECT_DIR to where this repository lives on the Airflow worker."""
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/competitor-price-tracker"

with DAG(
    dag_id="competitor_price_tracker",
    schedule="30 7 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="Africa/Tunis"),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=10)},
    tags=["scraping"],
) as dag:
    BashOperator(
        task_id="daily_run",
        bash_command=f"cd {PROJECT_DIR} && .venv/bin/python -m tracker run",
        execution_timeout=timedelta(minutes=45),
    )
