FROM python_base_p2p:latest

COPY . .

RUN dos2unix ./scripts/docker_run_static_checks.sh
RUN chmod +x ./scripts/docker_run_static_checks.sh

RUN dos2unix ./scripts/docker_run_tests.sh
RUN chmod +x ./scripts/docker_run_tests.sh

CMD sleep infinity
