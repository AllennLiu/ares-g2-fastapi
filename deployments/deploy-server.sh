#!/bin/bash

ERROR_COUNT=0
RED='\033[0;31m'
YELLOW='\033[0;33m'
CRESET='\033[0m'
DEPLOY_YAML="deployments/deploy-server.yml"
SERVICE_NAME=$(grep serviceName: $DEPLOY_YAML | awk -F\: '{print $NF}' | tr -d ' ')

# configure deployment/cronjobs settings
sed -i "s,<CI_REGISTRY_IMAGE>,${CI_REGISTRY_IMAGE}:${VERSION},g" deployments/deploy-*.yml
sed -i "s,<CI_REGISTRY_IMAGE>,${CI_REGISTRY_IMAGE}:${VERSION},g" cronjobs/deploy-*.yml

more << EOF
Show Deploy/Service/Ingress Config:
===========================================================================
$(cat $DEPLOY_YAML)
===========================================================================
EOF

# apply deploy/service to cluster
# (configmap has been created by API trigger of web-config-set project)
kubectl apply -f $DEPLOY_YAML --record || ERROR_COUNT=$(( ERROR_COUNT + 1 ))
sleep 30

more << EOF

===========================================================================
Show Deployment Pods Status:
===========================================================================
$(kubectl -n kube-ops get po -o wide | grep -v '\-cron' | grep $SERVICE_NAME)
===========================================================================
EOF

# apply cronjobs config to cluster
more << EOF
Show Cronjobs Config:
===========================================================================
$(cat cronjobs/deploy-cronjob.yml)
===========================================================================
EOF
kubectl delete -f cronjobs/deploy-cronjob.yml
sleep 10
kubectl apply -f cronjobs/deploy-cronjob.yml || ERROR_COUNT=$(( ERROR_COUNT + 1 ))
sleep 30

more << EOF

===========================================================================
Show Cronjobs Status:
===========================================================================
$(kubectl -n kube-ops get po -o wide | grep '^ares-g2-cron-')
===========================================================================
EOF

more << EOF
Show Nodes:
===========================================================================
$(kubectl get nodes)
===========================================================================
EOF

if [ $ERROR_COUNT -ne 0 ]; then
    echo -e " ${RED}*${CRESET} ${YELLOW}Something wrong occurred in" \
            "deployment of service/cron.${CRESET}"
fi
