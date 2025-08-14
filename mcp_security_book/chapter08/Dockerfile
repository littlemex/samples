FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y procps

COPY zombie_maker.sh /zombie_maker.sh
COPY signal_handler.sh /signal_handler.sh
RUN chmod +x /*.sh

CMD ["/signal_handler.sh"]
