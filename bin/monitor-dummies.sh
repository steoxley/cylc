#!/bin/bash

# display currently running external dummy tasks
    
HEADING1="Running External Dummy Tasks"
HEADING2=$(ps -fu $USER | grep UID | grep -v grep)

OIFS=$IFS
while true; do
    IFS=$OIFS
    FOO=$(ps -fu $USER | grep dummy | grep -v grep )
    clear
    IFS=$'\n'
    echo -e "\033[31m$HEADING1\033[0m"
    echo -e "\033[34m$HEADING2\033[0m"
    for line in $FOO
        do 
            echo -e "\033[33m$line\033[0m"
        done
    sleep 2
done

