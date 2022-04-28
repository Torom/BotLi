FROM debian:stable-slim
MAINTAINER BOTLI
RUN echo BOTLI
COPY . .
COPY requirements.txt .

RUN apt update > aptud.log && apt install -y wget python3 python3-pip p7zip-full > apti.log
RUN python3 -m pip install --no-cache-dir -r requirements.txt > pip.log

RUN mv config.yml.default config.yml
RUN bash sf.sh
RUN mv sf /engines

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

RUN chmod +x sf

CMD python3 user_interface.py
