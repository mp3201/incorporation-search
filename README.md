Scraper for search of incorporation data
====================

Most U.S. based firms incorporate in a U.S. state or states through their secretary of states.  For over 35 U.S. states, one can view basic information about these incorporated firms online.  This python program includes a list of states for which scraping is possible and the specific conditions to extract the maximum amount of information from each result.


Caveats
-------------------

Users of this script take full responsibility for any legal issues surrounding web scraping.  All the sites included in the script are public institutions and the script was written for academic research purposes.

Installation
-------------------

The script is run in the terminal (command line) and requires at least Python 2.7.  You also need the BeautifulSoup and selenium Python modules.

Additional requirements
-------------------

The scraper performs best in either Chrome or Firefox (with WebDriver) installed.  The browser must be open to run the script.  Next, the script assumes the existence of an input file of the form:

    id1,id2,company-name,two-letter state abbreviation

Use
-------------------

After installation, cd to the directory where the script resides.  Make sure that this folder contains two pieces:

- input file
- output folder

Then run the command

    python "get_company_choice.py" -i inputFile.csv -m 1 -x 3 -c outputFolder

The "-m" is the minimum time between scrapes (i.e. be kind to these websites!).  The "-x" is the maximum wait time between scrapes.

Additional use
------------------

Sort the input file randomly so you hit the state websites at different times.

Strings for company names are messy.  They can include "Inc.", "Corp." etc.  I suggest recreating a new file of the failed search results from the first run.  All these company names can be pruned to exclude common strings and then the script can be re-run (with a new input file name and output folder name). 

Next, many companies incorporate in Delaware and/or California along with their home state.  The easiest way to get these additional results is to recreate the main input file, duplicate all non-CA/DE firms and replace their state with DE and CE separately.  You can then run the script again with just these two states as the search.
