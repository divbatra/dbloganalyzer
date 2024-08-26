FROM python:3.11-slim as build-stage
ENV PYHTONUNBUFFERED=1
#RUN apt-get update && apt-get -y install tesseract-ocr
#RUN apt-get -y install ffmpeg libsm6 libxext6
#RUN apt-get install -y poppler-utils
WORKDIR /function
ADD requirements.txt /function/
                        RUN pip3 install --target /python/  --no-cache --no-cache-dir -r requirements.txt &&\
                            rm -fr ~/.cache/pip /tmp* requirements.txt func.yaml Dockerfile .venv &&\
                            chmod -R o+r /python
ADD . /function/
RUN rm -fr /function/.pip_cache
RUN chmod -R o+r /function
ENV PYTHONPATH=/function:/python
ENTRYPOINT ["/python/bin/fdk", "/function/func.py", "handler"]
RUN mkdir -p /home/opc/loganalyzer
COPY config /home/opc/loganalyzer
COPY key.pem /home/opc/loganalyzer


