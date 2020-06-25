FROM nginx

RUN apt-get update && apt-get install -y python3 python3-pip

COPY requirements.txt /srv/
RUN pip3 install -r /srv/requirements.txt

COPY src/index.html /usr/share/nginx/html/
COPY src/vis-network.min.js /usr/share/nginx/html/

RUN echo '{}' > /usr/share/nginx/html/data.json
COPY /src/update.sh .
COPY /src/update.py .
