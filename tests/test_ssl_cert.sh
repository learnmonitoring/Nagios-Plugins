#!/usr/bin/env bash
#  vim:ts=4:sts=4:sw=4:et
#
#  Author: Hari Sekhon
#  Date: 2015-10-07 13:41:58 +0100 (Wed, 07 Oct 2015)
#
#  https://github.com/harisekhon/nagios-plugins
#
#  License: see accompanying Hari Sekhon LICENSE file
#
#  If you're using my code you're welcome to connect with me on LinkedIn and optionally send me feedback to help improve or steer this or other code I publish
#
#  https://www.linkedin.com/in/harisekhon
#

set -euo pipefail
[ -n "${DEBUG:-}" ] && set -x
srcdir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$srcdir/..";

. ./tests/utils.sh

echo "
# ============================================================================ #
#                                S S L   C e r t
# ============================================================================ #
"

$perl -T ./check_ssl_cert.pl -H www.google.com -d www.google.com -w 2 -c 1 -v # -t 20
hr
set +e
$perl -T ./check_ssl_cert.pl -H www.google.com -d wrongdomain.com -w 2 -c 1 -v # -t 20
check_exit_code 2
set -e
hr
$perl -T ./check_ssl_cert.pl -H signin.ebay.com --domain signin.ebay.com --subject-alternative-name signin.ebay.co.uk,signin.ebay.de -w 2 -c 1 -v # -t 20
hr
set +e
$perl -T ./check_ssl_cert.pl -H signin.ebay.com -d signin.ebay.com --subject-alternative-name nonexistent.co.uk -w 2 -c 1 -v # -t 20
check_exit_code 2
set -e
hr
echo; echo
