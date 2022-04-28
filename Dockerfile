FROM python:3.10.4-bullseye
MAINTAINER BOTLI
RUN echo BOTLI
COPY . .
COPY requirements.txt .

RUN mv config.yml.default config.yml
RUN bash sf.sh
RUN mv sf /engines

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

RUN chmod +x sf

CMD python3 user_interface.py
