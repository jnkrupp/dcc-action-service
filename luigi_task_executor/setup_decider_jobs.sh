#!/bin/bash

#exit script if we try to use an uninitialized variable.
set -o nounset
#exit the script if any statement returns a non-true return value
set -o errexit


#set up AWS config credentials file so the deciders can creat and write the touch files with AWS CLI
#set variables to default values if they are not already set
#http://stackoverflow.com/questions/2013547/assigning-default-values-to-shell-variables-with-a-single-command-in-bash
: ${AWS_SECRET_ACCESS_KEY:=aws_secret_access_key}
: ${AWS_ACCESS_KEY_ID:=aws_access_key_id}
: ${AWS_REGION:=aws_region}

mkdir -p /home/ubuntu/.aws
aws_str=$'[default]\naws_secret_access_key = '"${AWS_SECRET_ACCESS_KEY}"$'\naws_access_key_id = '"${AWS_ACCESS_KEY_ID}"$'\nregion = '"${AWS_REGION}"
echo "$aws_str" > /home/ubuntu/.aws/config

#set variables to default values if they are not already set
#http://stackoverflow.com/questions/2013547/assigning-default-values-to-shell-variables-with-a-single-command-in-bash
: ${CONSONANCE_WEB_SERVICE:=consonance_web_service}
: ${CONSONANCE_TOKEN:=consonance_token}
#set up Consonance credentials so the deciders can call Consonance to launch the instances
mkdir -p /home/ubuntu/.consonance
consonance_str=$'[webservice]\nbase_path = '"${CONSONANCE_WEB_SERVICE}"$'\ntoken = '"${CONSONANCE_TOKEN}"
echo "$consonance_str" > /home/ubuntu/.consonance/config

#start the Luigi daemon in the background
#so the action service that monitors tasks
#can get information on tasks
#assume we are in the right directory as setup in the Dockerfile
sudo luigid --background

#run cron in forground so container doesn't stop
#if cron is run without '-f' it will launch cron
#in the background the command will end and the 
#container will exit. 
#The Docker container should be
#run in the background with the '-d' switch so it doesn't
#block the terminal
sudo cron -f 

#for testing:
#run cron in background and run tail so container
#doesn't exit and we can see log 
#sudo cron && sudo tail -f /tmp/decider_log

