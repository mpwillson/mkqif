#!/bin/sh
#
# Run simple tests
#

SCRIPT=${0##*/}
TESTDIR="./test"
GOLD="${TESTDIR}/results.gold"
RESULTS="${TESTDIR}/results"
makegold=""

if [ ! -d ${TESTDIR} ]; then
    echo "${SCRIPT}: can't find ${TESTDIR} directory"
    exit 1
fi

if [ ! -r ${GOLD} ]; then
    makegold=1
fi

while [ $# -gt 0 ]; do
    case $1 in
        -g)
            makegold=1
            ;;
        *)
            echo ${SCRIPT}: unknown option: $1
            exit 1
    esac
    shift
done

# run smoke tests
./mkqif.py -f test/barclays.cfg -e 17-06-2021 -sn \
           >${RESULTS} 2>&1
# same as above, but output to file
./mkqif.py -f test/barclays.cfg -e 17-06-2021 -n \
           >>${RESULTS} 2>&1
cat test/barclays210617.qif >>${RESULTS} 2>&1
rm -f test/barclays210617.qif
./mkqif.py -f test/barclays.cfg -e 17-06-2021 -sn barclays,test/barclays.csv \
           >>${RESULTS} 2>&1
./mkqif.py -f test/test.cfg -e 05-06-2019 -sn test,test/test.csv \
           >>${RESULTS} 2>&1
./mkqif.py -f test/test.cfg -e 20-06-2022 -sn test,test/test1.csv \
           >>${RESULTS} 2>&1
./mkqif.py -f test/ncols.cfg -e 20-06-2022 -sn  test,test/test1.csv \
           >>${RESULTS} 2>&1
./mkqif.py -f test/empty.cfg -e 20-06-2022 -sn test,test/test1.csv \
           >>${RESULTS} 2>&1

if [ "${makegold}" = "1" ]; then
    mv ${RESULTS} ${GOLD}
    echo ${SCRIPT}: ${GOLD} created
else
    diff -u ${GOLD} ${RESULTS}
    if [ $? -eq 0 ]; then
        echo "${SCRIPT}: all tests passed"
    fi
fi
