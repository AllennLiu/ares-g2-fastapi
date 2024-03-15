#!/bin/bash

LOOP_KEEP=True
WORKDIR=$PWD
SERVE_PORT=8787
SERVE_HOST=0.0.0.0

# SSH client public key
SSH_PUB_KEY='ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCxrbvTeCCQvOvMQqh98MPuJxpNlAwYQUueGrY1Z3byoNuR1bThjSAq9DGG6ANuRzrHDtxPXRxURQensNJdmKN0s37tpyvbvYV5Zjg0xUWgTpP+7QCzPGzXdsONZ6CR7cUL3phClMVnUFhERZ56gU+CqBHpFJskT9Qf2nxlTPf+1UFwlDag21Vi756u81wXyMUYs2GNQjVSnCF/5U92CSsNqENifxfEDdCyCmqTm9FntCH/wT8eHL0earjGPM4Jr83QtXjncxIwoqpSkrOAPq7s/0fSKrnYbb+RfMKKyIt5dxCM0HCNgfoDaVYuwp0fu5ujuR3Prdy3ert9UTMWp9/e2iMJsskb3O3nP3I45fO8vOWF9vX0ZM+Ok/pWIPJlBY52jyKaTqU/QiqXGqoqs0XKhQnyfPn3gQQL/Py/0Kzsf4FP2zkoQhKRBRXpISU/4y5g/bpary5LBCZqmG7GlB/+98B337FJMR3nZHZXm1aBns+ElqDZiM4ix5jC7WipchSUW5RWV3RRhkqX9KrS0WdrhFGovzm22QseUwNJul7ZnSsYf6WiScGEAh5rZywfr0ZriAww65g9Vv/s47Wx4lbX3mlyjwFMSIUZkf4L3Prs2rQSelDTVs4zRxKWa9ZKOmNDe8YmrvK+LIQ/NX6CQB0wEmLHUBBstewdNBccXRy9Rw== ieciec070168@IPT-070168-HP'

# The number of workers formula: ( 2 x CPU_CORES ) + 1
CPU_CORE_NUM=$(python -c 'from multiprocessing import cpu_count; print(cpu_count())')
WORKER_NUM=$(( ( 2 * CPU_CORE_NUM ) + 1 ))
# Override system automated detected CPU cores for saving cluster resource

function usage
{
    more << EOF
Usage: $0 [Option] argv

FastAPI backend service manager.

Options:
  -s, --ssh       serve with SSH server only
  --stag, --test  serve environ with deployment
  --prod, --main  serve environ with production

EOF
    exit 0
}

function config_sshd
{
    # release limitation of log watch
    [ -z "$(grep -F fs.inotify.max_user_watches=524288 /etc/sysctl.conf)" ] && \
        echo fs.inotify.max_user_watches=524288 | tee -a /etc/sysctl.conf && sysctl -p

    # configure SSH settings
    echo 'root:111111' | chpasswd
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
    echo 'cd /usr/src >& /dev/null' >> /root/.bashrc
    service ssh start || true
    ssh-keygen -t rsa -N "" -f /root/.ssh/id_rsa <<< y
    echo $SSH_PUB_KEY > /root/.ssh/authorized_keys
}

function keyboard_interrupt
{
    LOOP_KEEP=False
}

function server_forever
{
    echo "Interrupted with CTRL+C to exited web service automatically."
    while [ "$LOOP_KEEP" == "True" ]; do sleep 1; done
}

function main
{
    config_sshd
    cd app
    uvicorn main:app --host $SERVE_HOST --port $SERVE_PORT --workers $WORKER_NUM --timeout-keep-alive 300
    cd $WORKDIR
    server_forever
    exit 0
}

# parse arguments
while [ -n "$1" ]
do
    case $1 in
        -h|--help)
            usage
            ;;
        -s|--ssh)
            config_sshd
            server_forever
            ;;
        --stag|--test)
            export FASTAPI_ENV=stag
            WORKER_NUM=1
            ;;
        --prod|--main)
            export FASTAPI_ENV=prod
            WORKER_NUM=10
            ;;
        * ) echo "Invalid arguments, try '-h/--help' for more information."
            exit 1
            ;;
    esac
    shift
done

# set terminate func
trap keyboard_interrupt 2

main
