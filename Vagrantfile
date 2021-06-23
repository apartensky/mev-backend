# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/focal64"

  config.vm.define "api", primary: true do |api|
    api.vm.hostname = "mev-api"

    api.vm.network "forwarded_port", guest: 80, host: 8080

    api.vm.provider "virtualbox" do |vb|
      vb.memory = 4096
      vb.cpus = 2
    end

    api.vm.provision :shell do |s|
      s.path = "vagrant/provision.sh"
      s.env = {
        environment:ENV["ENVIRONMENT"],
        db_name:ENV["DB_NAME"],
        db_user:ENV["DB_USER"],
        db_passwd:ENV["DB_PASSWD"],
        root_db_passwd:ENV["ROOT_DB_PASSWD"],
        db_port:ENV["DB_PORT"],
        db_host:ENV["DB_HOST_FULL"],

        # change as appropriate. For dev,
        frontend_domain:ENV["FRONTEND_DOMAIN"],
        domain:ENV["BACKEND_DOMAIN"],
        django_secret:ENV["DJANGO_SECRET_KEY"],

        # needed for production, but leave blank for local dev
        # In production, this is needed so that the connections
        # from the load balancer are accepted
        load_balancer_ip:"",

        # allows a dev frontend to talk to the API
        other_cors_origins:ENV["OTHER_CORS_ORIGINS"],
        django_superuser_passwd:ENV["DJANGO_SUPERUSER_PASSWORD"],
        django_superuser_email:ENV["DJANGO_SUPERUSER_EMAIL"],

        # Can leave blank for local dev since we are not using remote storage
        mev_storage_bucket:ENV["STORAGE_BUCKET_NAME"],

        # For dev, we only use local storage. All the unit tests mock out
        # connections to storage backends, but this is to be explicit and avoid
        # any checks that app startup performs.
        storage_location:ENV["STORAGE_LOCATION"],

        # For local dev, all the remote job runner calls are mocked in unit testing,
        # so we can turn this off.
        enable_remote_job_runners:ENV["ENABLE_REMOTE_JOB_RUNNERS"],

        # Only for cloud-based storage. Needed for url signing
        service_account_email:ENV["SERVICE_ACCOUNT"],

        # Emails are not send in dev, so we can leave most of these as blank
        email_backend:ENV["EMAIL_BACKEND_CHOICE"],
        from_email:ENV["FROM_EMAIL"],
        gmail_access_token:ENV["GMAIL_ACCESS_TOKEN"],
        gmail_refresh_token:ENV["GMAIL_REFRESH_TOKEN"],
        gmail_client_id:ENV["GMAIL_CLIENT_ID"],
        gmail_client_secret:ENV["GMAIL_CLIENT_SECRET"],

        sentry_url:ENV["SENTRY_URL"],
        dockerhub_username:ENV["DOCKERHUB_USERNAME"],
        dockerhub_passwd:ENV["DOCKERHUB_PASSWORD"],
        dockerhub_org:ENV["DOCKERHUB_ORG"],
        cromwell_bucket:ENV["CROMWELL_BUCKET"],
        cromwell_ip:ENV["CROMWELL_IP"],
        branch:ENV["BRANCH"]
      }
    end
  end

  config.vm.define "cromwell", autostart: false do |cromwell|
    cromwell.vm.hostname = "mev-cromwell"

    cromwell.vm.provider "virtualbox" do |vb|
      vb.memory = 1024
      vb.cpus = 2
    end

    cromwell.vm.provision "shell", inline: <<-SHELL
      # https://serverfault.com/a/670688
      export DEBIAN_FRONTEND=noninteractive
      # exit immediately on errors in any command
      set -e
      # print commands and their expanded arguments
      set -x

      # install Puppet
      CODENAME=$(/usr/bin/lsb_release -sc)
      /usr/bin/curl -sO "https://apt.puppetlabs.com/puppet6-release-$CODENAME.deb"
      /usr/bin/dpkg -i "puppet6-release-$CODENAME.deb"
      /usr/bin/apt-get -qq update
      /usr/bin/apt-get -qq -y install puppet-agent

      # install and configure librarian-puppet
      /opt/puppetlabs/puppet/bin/gem install librarian-puppet -v 3.0.1 --no-document
      /opt/puppetlabs/puppet/bin/librarian-puppet config path /opt/puppetlabs/puppet/modules --global
      /opt/puppetlabs/puppet/bin/librarian-puppet config tmp /tmp --global
      PATH="${PATH}:/opt/puppetlabs/bin" && cd /vagrant/deploy/puppet && /opt/puppetlabs/puppet/bin/librarian-puppet install

      /opt/puppetlabs/bin/puppet apply /vagrant/deploy/puppet/manifests/site.pp
    SHELL
  end
end
