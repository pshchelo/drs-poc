FROM python:3.10-slim
RUN apt-get update && apt-get install -y git build-essential
ADD . /opt
RUN pip install /opt/
