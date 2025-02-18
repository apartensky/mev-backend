#! /bin/bash

# Immediately fail if anything goes wrong.
set -e

# print commands and their expanded arguments
set -x

#################### Start ENV variables #################################
# This section contains environment variables that are populated
# by terraform as part of its templatefile function

set -o allexport

source /vagrant/$1

# Some "extra" setup of environment varibles below

ENVIRONMENT="dev"


# A comma-delimited list of the hosts.  Add hosts as necessary
# e.g. 127.0.0.1,localhost,xx.xxx.xx.xx,mydomain.com
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# A comma-delimited list of the origins for cors requests
# Needed to hookup to front-end frameworks which may be 
# at a different domain. Include protocol and ports
DJANGO_CORS_ORIGINS=https://$FRONTEND_DOMAIN,$OTHER_CORS_ORIGINS

# Where is redis listening?
# We assume that it is listening on the default port of 6379
REDIS_HOST=localhost

# the path to a JSON file containing the credentials to authenticate with the Google storage API.
# The startup script will perform the authentication and place the credentials into this file.
# Note that this authentication can ONLY happen if we are on GCP and can use the VMs service
# account.
# For local dev that does not interact with a google bucket, that authentication doesn't
# happen and we simply "touch" this file.
STORAGE_CREDENTIALS="/vagrant/storage_credentials.json"

# If using local storage for all files (not recommended since sequencing files
# could consume large amount of disk space), set the following:
# This directory is relative to the django BASE_DIR
LOCAL_STORAGE_DIRNAME=user_resources

# For signing download URLs we need a credentials file. To create that, we need a
# service account with appropriate privileges. This variable is the full name of that
# service account file (e.g. <id>@project.iam.gserviceaccount.com)
# For local dev, can leave as-is
SERVICE_ACCOUNT="id@project.iam.gserviceaccount.com"

# set the directory where the MEV src will live. Used by the supervisor conf files
MEV_HOME=/vagrant/mev

set +o allexport

#################### End ENV variables #################################


# Install some dependencies
apt-get update \
    && apt-get install -y \
    build-essential \
    apt-transport-https \
    ca-certificates \
    gnupg2 \
    software-properties-common \
    zlib1g-dev \
    libssl-dev \
    libncurses5-dev \
    libreadline-dev \
    libbz2-dev \
    libffi-dev \
    liblzma-dev \
    libsqlite3-dev \
    libpq-dev \
    wget \
    supervisor \
    nano \
    git \
    curl \
    pkg-config \
    netcat \
    procps \
    postgresql-12 \
    python3-pip \
    nginx \
    docker.io

# create the mev user and add them to the docker group
# so they are able to execute Docker containers
addgroup --system mev && adduser --system --group mev
usermod -aG docker mev

# Create a directory where we will download/install our software
mkdir /opt/software

# Install Python 3.7.6. Ends up in /usr/local/bin/python3
cd /opt/software && \
  wget https://www.python.org/ftp/python/3.7.6/Python-3.7.6.tgz && \
  tar -xzf Python-3.7.6.tgz && \
  cd Python-3.7.6 && \
  ./configure && \
  make && \
  make install

# Install redis
cd /opt/software && \
  wget https://download.redis.io/releases/redis-6.2.1.tar.gz
  tar -xzf redis-6.2.1.tar.gz && \
  cd redis-6.2.1 && \
  make && \
  make install

# Install the python packages we'll need:
cd /vagrant && \
  cd mev && \
  /usr/local/bin/pip3 install -U pip && \
  /usr/local/bin/pip3 install --no-cache-dir -r ./requirements.txt

# setup some static environment variables
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# Copy the various supervisor conf files to the appropriate locations
cd /vagrant/deploy/mev/supervisor_conf_files && \
cp redis.conf /etc/supervisor/conf.d/ && \
cp celery_worker.conf /etc/supervisor/conf.d/ && \
cp celery_beat.conf /etc/supervisor/conf.d/ && \
cp gunicorn.conf /etc/supervisor/conf.d/


# Copy the nginx config file, removing the existing default
rm -f /etc/nginx/sites-enabled/default
cp /vagrant/deploy/mev/nginx.conf /etc/nginx/sites-enabled/

# Create the log directory and the dir from which nginx will
# eventually serve static files
mkdir -p /var/log/mev
mkdir -p /www

# touch some log files which will then be transferred to the mev 
# user.
touch /var/log/mev/celery_beat.log  \
  /var/log/mev/celery_worker.log  \
  /var/log/mev/cloud_sql.log  \
  /var/log/mev/gunicorn.log  \
  /var/log/mev/redis.log

# Give the mev user ownership of the code directory and the logging directory
chown -R mev:mev /var/log/mev /www
 
# use localhost when we're in dev. the postgres server is local
export DB_HOST_SOCKET=$DB_HOST_FULL

# Specify the appropriate settings file.
# We do this here so it's prior to cycling the supervisor daemon
export DJANGO_SETTINGS_MODULE=mev.settings_dev

# Generate a set of keys for signing the download URL for bucket-based files.
# Don't really need this for local dev, but it needs to be populated for the app
# to startup properly
touch $STORAGE_CREDENTIALS

# First restart supervisor since it needs access to the
# environment variables (can only read those that are defined
# when the supervisor daemon starts)
service supervisor stop
supervisord -c /etc/supervisor/supervisord.conf
supervisorctl reread

# Give it some time to setup the socket to the db
sleep 3

# Setup the database.
runuser -m postgres -c "psql -v ON_ERROR_STOP=1 --username "postgres" --dbname "postgres" <<-EOSQL
    CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWD';
    CREATE DATABASE $DB_NAME;
    GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
    ALTER USER $DB_USER CREATEDB;
EOSQL"

# Some preliminaries before we start asking django to set things up:
mkdir -p /vagrant/mev/pending_user_uploads
mkdir -p /vagrant/mev/resource_cache
mkdir -p /vagrant/mev/operation_staging
mkdir -p /vagrant/mev/operations
mkdir -p /vagrant/mev/operation_executions

# Change the ownership so we have write permissions.
chown -R mev:mev /vagrant/mev

### DANGER-- 777 permissions to get this to work. Only for local dev.
chmod -R 777 /vagrant/mev

# Apply database migrations, collect the static files to server, and create
# a superuser based on the environment variables passed to the container.
/usr/local/bin/python3 /vagrant/mev/manage.py makemigrations api
/usr/local/bin/python3 /vagrant/mev/manage.py migrate
/usr/local/bin/python3 /vagrant/mev/manage.py createsuperuser --noinput

# The collectstatic command gets all the static files 
# and puts them at /vagrant/mev/static.
# We them copy the contents to /www/static so nginx can serve:
/usr/local/bin/python3 /vagrant/mev/manage.py collectstatic --noinput
cp -r /vagrant/mev/static /www/static

# Populate a "test" database, so the database
# will have some content to query.
if [ $POPULATE_DB = 'yes' ]; then
    /usr/local/bin/python3 /vagrant/mev/manage.py populate_db
fi

# Add on "static" operations, such as the dropbox uploaders, etc.
# Other operations (such as those used for a differential expression
# analysis) are added by admins once the application is running.
# Temporarily commented to avoid the slow build.
if [ $ENVIRONMENT != 'dev' ]; then
  /usr/local/bin/python3 /vagrant/mev/manage.py add_static_operations
fi
# Start and wait for Redis. Redis needs to be ready before
# celery starts.
supervisorctl start redis
echo "Waiting for Redis..."
while ! nc -z $REDIS_HOST 6379; do
  sleep 2
done
echo "Redis started!"

# Start celery:
supervisorctl start mev_celery_beat
supervisorctl start mev_celery_worker

# Restart nginx so it loads the new config:
service nginx restart

# Add to the vagrant user's ~/.profile so that the environment variables
# are "ready" after you SSH into the VM
echo "source /vagrant/vagrant/final_setup.sh /vagrant/"$1 >> /home/vagrant/.profile