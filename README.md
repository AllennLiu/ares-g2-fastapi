SIT-Web-FastAPI
==================

## Version
`Rev: 2.1.15`

---

## Python Version
Require: `3.9.0`**+**

---

## Status

[![pipeline status](http://ipt-gitlab.ies.inventec:8081/TA-Web/SIT-Web-FastAPI/badges/master/pipeline.svg)](http://ipt-gitlab.ies.inventec:8081/TA-Web/SIT-Web-FastAPI/commits/master) [![coverage report](http://ipt-gitlab.ies.inventec:8081/TA-Web/SIT-Web-FastAPI/badges/master/coverage.svg)](http://ipt-gitlab.ies.inventec:8081/TA-Web/SIT-Web-FastAPI/-/commits/master)

---

## Description

Pod deploy application name ➠ `ares-g2-fastapi` *(namespace: `kube-ops`)*

  - **{+ Production +}**
    - [x] Docs ➠ [http://ares-g2-fastapi.cloudnative.ies.inventec/docs](http://ares-g2-fastapi.cloudnative.ies.inventec/docs)
    - [x] SPECs ➠ [http://ares-g2-fastapi.cloudnative.ies.inventec/redoc](http://ares-g2-fastapi.cloudnative.ies.inventec/redoc)
  - **{- Staging -}**
    - [x] Docs ➠ [http://ares-g2-fastapi.cloud.sit.ipt.inventec/docs](http://ares-g2-fastapi.cloud.sit.ipt.inventec/docs)
    - [x] SPECs ➠ [http://ares-g2-fastapi.cloud.sit.ipt.inventec/redoc](http://ares-g2-fastapi.cloud.sit.ipt.inventec/redoc)
  - **Cluster Internal Access**
    - [x] Access servie using app name → [http://ares-g2-fastapi:8787](http://ares-g2-fastapi:8787)

---

## Usage

  - Build Image

    ```bash
    $ docker build --no-cache -t registry.ipt-gitlab:8081/ta-web/sit-web-fastapi:${VERSION} .
    $ docker push registry.ipt-gitlab:8081/ta-web/sit-web-fastapi:${VERSION}
    ```

  - Docker Container Deployment

    ```bash
    $ docker run -tid \
          --add-host ipt-gitlab.ies.inventec:10.99.104.242 \
          --add-host mailrelay-b.ies.inventec:10.99.2.61 \
          -p 8787:8787 \
          -p 8788:22 \
          --volume /etc/localtime:/etc/localtime:ro \
          --privileged=true \
          --restart=always \
          --name ipt-fastapi \
          registry.ipt-gitlab:8081/ta-web/sit-web-fastapi:${VERSION} \
          bash service.sh --stag
    ```

  - Kubernetes Cluster Deployment

    ```bash
    $ kubectl delete -f deployments/deploy-server.yml
    $ sleep 1m
    $ kubectl apply -f deployments/deploy-server.yml --record
    ```

---

## Validation

<details>
<summary>點我顯示/關閉更多驗證資訊。</summary>
<ul>
  <li>None.</li>
</ul>
</details>

  - **Latest script has been validated by Liu.AllenJH on K8S-Cluster at 2021-05-30.**

## Reference

  - Flask x Vue - [https://learnku.com/python/t/24985](https://learnku.com/python/t/24985)
