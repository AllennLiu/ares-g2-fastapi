FROM registry.ipt-gitlab:8081/ta-web/sit-flask-api/node-base:python3.9-nodejs17-slim

ENV TZ="Asia/Taipei"

ENV NODE_SOURCE /usr/src

COPY . $NODE_SOURCE

WORKDIR $NODE_SOURCE

RUN date && apt-key add ./deployments/pubkey.gpg

RUN apt-get update && \
    apt-get install -y gcc g++ make libncurses5-dev libncursesw5-dev ncurses-dev && \
    cd tools && tar zxvf vim74.tar.gz && cd vim74 && \
    ./configure --prefix=/usr \
                --with-features=huge \
                --disable-selinux \
                --enable-pythoninterp \
                --enable-cscope \
                --enable-multibyte && \
    make && make install && ln -s /usr/local/bin/vim /usr/local/bin/vi

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl git libhiredis-dev \
        ssh sshpass plink telnet unzip apache2-utils \
        build-essential \
        unixodbc unixodbc-dev tesseract-ocr

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir openai==1.3.7 || true

RUN echo 'alias vi="vim"' >> ~/.bashrc

EXPOSE 8787 22

USER root

ENV PYTHONIOENCODING utf-8

CMD ["bash", "service.sh", "--prod"]
