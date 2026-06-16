FROM python:3.11-slim

WORKDIR /app

COPY web/ /app/
COPY agents/trip-planner/data/zalopay_flight_est_price.json /app/data/
COPY agents/trip-planner/data/zalopay_hotel_est_price.json /app/data/
COPY agents/trip-planner/data/zalopay_train_est_price.json /app/data/
COPY agents/trip-planner/data/zalopay_bus_est_price.json /app/data/
COPY agents/trip-planner/data/vn_flight_estimates.json /app/data/
COPY agents/trip-planner/data/zalopay_flight_qr_link.jpg /app/data/qr/
COPY agents/trip-planner/data/zalopay_hotel_qr_link.jpg /app/data/qr/
COPY agents/trip-planner/data/zalopay_train_qr_link.jpg /app/data/qr/
COPY agents/trip-planner/data/zalopay_bus_qr_link.jpg /app/data/qr/

ENV PORT=8080
EXPOSE 8080

# Browser config (config.js is gitignored; ship example as runtime default)
RUN cp /app/config.example.js /app/config.js

CMD ["python3", "proxy.py"]
