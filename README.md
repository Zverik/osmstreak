## What is OSM Streak ##

OSM Streak makes you do small tasks for OpenStreetMap every day. The goal is to map every day for at least a year. Tasks are small, five minutes each. The point is to map every day, not map as much as you can. Persistence pays off.

## Try it ##

http://streak.osmz.ru

## Contribute ##

Feel free to:
*  do pull request
*  submit issues
*  create new challenges

## Translating ##

Translations can be done in transifex: https://www.transifex.com/openstreetmap/osm-streak/

## Develop ##

Prerequisites: a Linux OS or Mac OS since ruamel.yaml does not support emoji on Windows.

Install requirements: 
`pip install -r requirements.txt`

Run the app:
`./run.py`

### Add your account in streak.db ###

For tests purpose only, you can manualy add your account in the streak.db database:
1.  Open streak.db with sqlitebrowser or similar application
2.  Add a line in the user table:
    *  uid: your OSM uid. You can use http://whosthat.osmz.ru to get it
    *  name: your OSM login
    *  email: your email
    *  lang: your language code
    *  set score, streak and level to 0

### Create a new challenge ###

Create a new file in folder tasks. Have a look to other tasks to understand the syntax.

Then you can test a changeset against all the tasks with following command:
`./test_chargement.py`

## License ##

OSM Streak is released under the MIT license
