#!/usr/bin/perl -T
# nagios: -epn
#
#  Author: Hari Sekhon
#  Date: 2014-04-11 20:11:15 +0100 (Fri, 11 Apr 2014)
#
#  http://github.com/harisekhon
#
#  License: see accompanying LICENSE file
#

# still calling v1 for compatability with older CM versions
#
# http://cloudera.github.io/cm_api/apidocs/v1/index.html

$DESCRIPTION = "Nagios Plugin to check state of a service/role in Cloudera Manager via CM Rest API

You may need to upgrade to Cloudera Manager 4.6 for the Standard Edition (free) to allow the API to be used, but it should work on all versions of Cloudera Manager Enterprise Edition

This is still using v1 of the API for compatability purposes

Tested on Cloudera Manager 5.0.0";

$VERSION = "0.1";

use strict;
use warnings;
BEGIN {
    use File::Basename;
    use lib dirname(__FILE__) . "/lib";
}
use HariSekhonUtils;
use HariSekhon::ClouderaManager;

$ua->agent("Hari Sekhon $progname version $main::VERSION");

%options = (
    %hostoptions,
    %useroptions,
    %cm_options,
    %cm_options_list,
);

delete $options{"--hostId"};
delete $options{"--activityId"};
delete $options{"--nameservice"};

@usage_order = qw/host port user password tls ssl-CA-path tls-noverify cluster service roleId list-activities list-clusters list-hosts list-nameservices list-roles list-services/;

get_options();

$host       = validate_host($host);
$port       = validate_port($port);
$user       = validate_user($user);
$password   = validate_password($password);

vlog2;
set_timeout();

$status = "OK";

list_cm_components();

validate_cm_cluster_options();

cm_query();

my $state;
if($cluster and $service){
    $msg = "cluster '$cluster' service '$service'";
    if($role){
        check_cm_field("roleState");
        check_cm_field("type");
        if($verbose){
            $msg .= " role '$role'";
        } else {
            $msg .= " role '" . $json->{"type"} . "'"; 
        }
        $state = $json->{"roleState"};
    } else {
        check_cm_field("serviceState");
        $state = $json->{"serviceState"};
    }
} else {
    usage "for --check-state must specify --cluster and --service and optionally --role";
}
$msg .= " state=$state";
if($state eq "STARTED"){
    # ok
} elsif(grep { $state eq $_ } qw/STARTING STOPPING/){
    warning;
} elsif(grep { $state eq $_ } qw/STOPPED/){
    critical;
} elsif(grep { $state eq $_ } qw/UNKNOWN HISTORY_NOT_AVAILABLE/){
    unknown;
} else {
    unknown;
    $msg .= " (state unrecognized. $nagios_plugins_support_msg_api)";
}

quit $status, $msg;
