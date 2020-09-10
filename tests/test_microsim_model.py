import os
import pytest
import multiprocessing
import pandas as pd
import numpy as np
import copy
from microsim.microsim_model import Microsim
from microsim.column_names import ColumnNames
from microsim.activity_location import ActivityLocation

# ********************************************************
# These tests run through a whole dummy model process
# ********************************************************

test_dir = os.path.dirname(os.path.abspath(__file__))

# arguments used when calling the Microsim constructor. Usually these are the same
microsim_args = {"data_dir": os.path.join(test_dir, "dummy_data"),
                 "r_script_dir": os.path.normpath(os.path.join(test_dir, "..", "R/py_int")),
                 "testing": True, "debug": True,
                 "disable_disease_status": True, 'lockdown_file': ""}


# This 'fixture' means that other functions (e.g. step) can use the object created here.
# Note: Don't try to run this test, it will be called when running the others that need it, like `test_step()`.
@pytest.fixture()
def test_microsim():
    """Test the microsim constructor by reading dummy data. The microsim object created here can then be passed
    to other functions for them to do their tests
    """
    with pytest.raises(FileNotFoundError):
        # This should fail because the directory doesn't exist
        args = microsim_args.copy()
        args['data_dir'] = "./bad_directory"
        m = Microsim(**args)

    m = Microsim(**microsim_args)

    # Check that the dummy data have been read in correctly. E.g. check the number of individuals is
    # accurate, that they link to households correctly, that they have the right *flows* to the right
    # *destinations* and the right *durations* etc.

    assert len(m.individuals) == 17

    # Households
    # (The households df should be the same as the one in the corresponding activity location)
    assert m.activity_locations[f"{ColumnNames.Activities.HOME}"]._locations.equals(m.households)
    # All flows should be to one location (single element [1.0])
    for flow in m.individuals[f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_FLOWS}"]:
        assert flow == [1.0]

    # House IDs are the same as the row index
    assert False not in list(m.households.index == m.households.ID)

    # First two people live together in first household
    assert list(m.individuals.loc[0:1, :][f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_VENUES}"].values) == [[0], [0]]
    # This one lives on their own in the fourth house
    assert list(m.individuals.loc[9:9, :][f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_VENUES}"].values) == [[3]]
    # These three live together in the last house
    assert list(m.individuals.loc[13:15, :][f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_VENUES}"].values) == [[6], [6], [6]]

    # Workplaces
    # All flows should be to one location (single element [1.0])
    for flow in m.individuals[f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_FLOWS}"]:
        assert flow == [1.0]
    # First person is the only one who does that job
    assert len(list(m.individuals.loc[0:0, ][f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_VENUES}"]))
    job_index = list(m.individuals.loc[0:0, ][f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_VENUES}"])[0][0]
    for work_id in m.individuals.loc[1:len(m.individuals), f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_VENUES}"]:
        assert work_id[0] != job_index
    # Three people do the same job as second person
    job_index = list(m.individuals.loc[1:1, ][f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_VENUES}"])[0]
    assert list(m.individuals.loc[4:4, f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_VENUES}"])[0] == job_index
    assert list(m.individuals.loc[13:13, f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_VENUES}"])[0] == job_index
    # Not this person:
    assert list(m.individuals.loc[15:15, f"{ColumnNames.Activities.WORK}{ColumnNames.ACTIVITY_VENUES}"])[0] != job_index

    # Test Shops
    shop_locs = m.activity_locations[ColumnNames.Activities.RETAIL]._locations
    assert len(shop_locs) == 248
    # First person has these flows and venues
    venue_ids = list(m.individuals.loc[0:0, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_VENUES}"])[0]
    # flows = list(m.individuals.loc[0:0, f"Retail{ColumnNames.ACTIVITY_FLOWS}"])[0]
    # These are the venues in the filename:
    raw_venues = sorted([24, 23, 22, 21, 19, 12, 13, 25, 20, 17])
    # Mark counts from 1, so these should be 1 greater than the ids
    assert [x - 1 for x in raw_venues] == venue_ids
    # Check the indexes point correctly
    assert shop_locs.loc[0:0, ColumnNames.LOCATION_NAME].values[0] == "Co-op Lyme Regis"
    assert shop_locs.loc[18:18, ColumnNames.LOCATION_NAME].values[0] == "Aldi Honiton"

    # Test Schools (similar to house/work above) (need to do for primary and secondary)
    primary_locs = m.activity_locations[f"{ColumnNames.Activities.PRIMARY}"]._locations
    secondary_locs = m.activity_locations[f"{ColumnNames.Activities.SECONDARY}"]._locations
    # All schools are read in from one file, both primary and secondary
    assert len(primary_locs) == 350
    assert len(secondary_locs) == 350
    assert primary_locs.equals(secondary_locs)
    # Check primary and secondary indexes point to primary and secondary schools respectively
    for indexes in m.individuals.loc[:, f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_VENUES}"]:
        for index in indexes:
            assert primary_locs.loc[index, "PhaseOfEducation_name"] == "Primary"
    for indexes in m.individuals.loc[:, f"{ColumnNames.Activities.SECONDARY}{ColumnNames.ACTIVITY_VENUES}"]:
        for index in indexes:
            assert secondary_locs.loc[index, "PhaseOfEducation_name"] == "Secondary"

    # First person has these flows and venues to primary school
    # (we know this because, by coincidence, the first person lives in the area that has the
    # first area name if they were ordered alphabetically)
    list(m.individuals.loc[0:0, "area"])[0] == "E00101308"
    venue_ids = list(m.individuals.loc[0:0, f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_VENUES}"])[0]
    raw_venues = sorted([12, 110, 118, 151, 163, 180, 220, 249, 280])
    # Mark counts from 1, so these should be 1 greater than the ids
    assert [x - 1 for x in raw_venues] == venue_ids
    # Check the indexes point correctly
    assert primary_locs.loc[12:12, ColumnNames.LOCATION_NAME].values[0] == "Axminster Community Primary Academy"
    assert primary_locs.loc[163:163, ColumnNames.LOCATION_NAME].values[0] == "Milton Abbot School"

    # Second to last person lives in 'E02004138' which will be the last area recorded in Mark's file
    assert list(m.individuals.loc[9:9, "area"])[0] == "E02004159"
    venue_ids = list(m.individuals.loc[9:9, f"{ColumnNames.Activities.SECONDARY}{ColumnNames.ACTIVITY_VENUES}"])[0]
    raw_venues = sorted([335, 346])
    # Mark counts from 1, so these should be 1 greater than the ids
    assert [x - 1 for x in raw_venues] == venue_ids
    # Check these are both secondary schools
    for idx in venue_ids:
        assert secondary_locs.loc[idx, "PhaseOfEducation_name"] == "Secondary"
    # Check the indexes point correctly
    assert secondary_locs.loc[335:335, ColumnNames.LOCATION_NAME].values[0] == "South Dartmoor Community College"

    # Finished initialising the model. Pass it to other tests who need it.
    yield m  # (this could be 'return' but 'yield' means that any cleaning can be done here

    print("Cleaning up .... (actually nothing to clean up at the moment)")


# Test the home flows on the dummy data
def test_add_home_flows(test_microsim):
    ind = test_microsim.individuals  # save typine
    # Using dummy data I know that there should be 2 person in household ID 0:
    assert len(ind.loc[ind.House_ID == 0, :]) == 2
    # And 4 people in house ID 2
    assert len(ind.loc[ind.House_ID == 1, :]) == 3
    # And 1 in house ID 7
    assert len(ind.loc[ind.House_ID == 7, :]) == 1


def test_read_school_flows_data(test_microsim):
    """Check that flows to primary and secondary schools were read correctly """
    # Check priary and seconary have the same data (they're read together)
    primary_schools = test_microsim.activity_locations[f"{ColumnNames.Activities.PRIMARY}"]._locations
    secondary_schools = test_microsim.activity_locations[f"{ColumnNames.Activities.SECONDARY}"]._locations
    assert primary_schools.equals(secondary_schools)
    # But they don't point to the same dataframe
    primary_schools["TestCol"] = 0
    assert "TestCol" not in list(secondary_schools.columns)

    schools = primary_schools  # Just refer to them with one name

    # Check correct number of primary and secondary schools
    # (these don't need to sum to total schools because there are a couple of nurseries in there
    assert len(schools) == 350
    primary_schools = schools.loc[schools.PhaseOfEducation_name == "Primary"]
    secondary_schools = schools.loc[schools.PhaseOfEducation_name == "Secondary"]
    len(primary_schools) == 309
    len(secondary_schools) == 39

    # Check all primary flows go to primary schools and secondary flows go to secondary schools
    primary_flows = test_microsim.activity_locations[f"{ColumnNames.Activities.PRIMARY}"]._flows
    secondary_flows = test_microsim.activity_locations[f"{ColumnNames.Activities.SECONDARY}"]._flows
    # Following slice slice gives the total flow to each of the 350 schools (sum across rows for each colum and then
    # drop the first two columns which are area ID and Code)
    for school_no, flow in enumerate(primary_flows.sum(0)[2:]):
        if flow > 0:
            assert schools.iloc[school_no].PhaseOfEducation_name == "Primary"
    for school_no, flow in enumerate(secondary_flows.sum(0)[2:]):
        if flow > 0:
            assert schools.iloc[school_no].PhaseOfEducation_name == "Secondary"


def test_read_msm_data(test_microsim):
    """Checks the individual microsimulation data are read correctly"""
    assert len(test_microsim.individuals) == 17
    assert len(test_microsim.households) == 8
    # Check correct number of 'homeless' (this is OK because of how I set up the data)
    with pytest.raises(Exception) as e:
        Microsim._check_no_homeless(test_microsim.individuals, test_microsim.households, warn=False)
        # This should reaise an exception. Get the number of homeless. Should be 15
        num_homeless = [int(s) for s in e.message.split() if s.isdigit()][0]
        print(f"Correctly found homeless: {num_homeless}")
        assert num_homeless == 15


# No longer updating disease counts. This can be removed.
# def test_update_disease_counts(test_microsim):
#     """Check that disease counts for MSOAs and households are updated properly"""
#     m = test_microsim  # less typing
#     # Make sure no one has the disease to start with
#     m.individuals[ColumnNames.DISEASE_STATUS] = 0
#     # (Shouldn't use _PID any more, this is a hangover to old version, but works OK with dummy data)
#     m.individuals.loc[9, ColumnNames.DISEASE_STATUS] = 1  # lives alone
#     m.individuals.loc[13, ColumnNames.DISEASE_STATUS] = 1  # Lives with 3 people
#     m.individuals.loc[11, ColumnNames.DISEASE_STATUS] = 1  # | Live
#     m.individuals.loc[12, ColumnNames.DISEASE_STATUS] = 1  # | Together
#     # m.individuals.loc[:, ["PID", "HID", "area", ColumnNames.DISEASE_STATUS, "MSOA_Cases", "HID_Cases"]]
#     m.update_disease_counts()
#     # This person has the disease
#     assert m.individuals.at[9, "MSOA_Cases"] == 1
#     assert m.individuals.at[9, "HID_Cases"] == 1
#     # These people live with someone who has the disease
#     for p in [13, 14, 15]:
#         assert m.individuals.at[p, "MSOA_Cases"] == 1
#         assert m.individuals.at[p, "HID_Cases"] == 1
#     # Two people in this house have the disease
#     for p in [11, 12]:
#         assert m.individuals.at[p, "MSOA_Cases"] == 2
#         assert m.individuals.at[p, "HID_Cases"] == 2
#
#     # Note: Can't fully test MSOA cases because I don't have any examples of people from different
#     # households living in the same MSOA in the test data


def test_change_behaviour_with_disease(test_microsim):
    """Check that individuals behaviour changed correctly with the disease status"""
    m = copy.deepcopy(test_microsim)  # less typing and so as not to interfere with other tests
    # Give some people the disease (these two chosen because they both spend a bit of time in retail
    p1 = 1
    p2 = 6
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC  # Behaviour change
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.PRESYMPTOMATIC  # No change

    m.step()
    m.change_behaviour_with_disease()  # (this isn't called by default when testing)

    # Nothing should have happended as we hadn't indicated a change in disease status
    for p, act in zip([p1, p1, p2, p2], [ColumnNames.Activities.HOME, ColumnNames.Activities.RETAIL,
                                         ColumnNames.Activities.HOME, ColumnNames.Activities.RETAIL]):
            assert m.individuals.loc[p, f"{act}{ColumnNames.ACTIVITY_DURATION}"] == \
               m.individuals.loc[p, f"{act}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]

    # Mark behaviour changed then try again
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS_CHANGED] = True
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS_CHANGED] = True

    m.step()
    m.change_behaviour_with_disease()  # (this isn't called by default when testing)

    # First person should spend more time at home and less at work
    assert m.individuals.loc[p1, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION}"] < m.individuals.loc[
        p1, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]
    assert m.individuals.loc[p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] > m.individuals.loc[
        p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]
    # Second person should be unchanged
    assert m.individuals.loc[p2, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION}"] == m.individuals.loc[
        p2, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]
    assert m.individuals.loc[p2, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] == m.individuals.loc[
        p2, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]

    # Mark behaviour changed then try again
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS_CHANGED] = True
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS_CHANGED] = True

    m.step()
    m.change_behaviour_with_disease()  # (this isn't called by default when testing)

    # First person should spend more time at home and less at work
    assert m.individuals.loc[p1, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION}"] < m.individuals.loc[
        p1, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]
    assert m.individuals.loc[p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] > m.individuals.loc[
        p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]

    # Second person should be unchanged
    assert m.individuals.loc[p2, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION}"] == m.individuals.loc[
        p2, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]
    assert m.individuals.loc[p2, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] == m.individuals.loc[
        p2, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]

    # First person no longer infectious, behaviour should go back to normal
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.RECOVERED
    m.step()
    m.change_behaviour_with_disease()  # (this isn't called by default when testing)
    assert m.individuals.loc[p1, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION}"] == m.individuals.loc[
        p1, f"{ColumnNames.Activities.RETAIL}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]
    assert m.individuals.loc[p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] == m.individuals.loc[
        p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION_INITIAL}"]


def test_update_venue_danger_and_risks(test_microsim):
    """Check that the current risk is updated properly"""
    # This is actually tested as part of test_step
    assert True

def test_hazard_multipliers(test_microsim):
    """
    This tests whether hazards for particular disease statuses or locations are multiplied properly.
    The relevant code is in update_venue_danger_and_risks().

    :param test_microsim: This is a pointer to the initialised model. Dummy data will have been read in,
    but no stepping has taken place yet."""
    m = copy.deepcopy(test_microsim)  # For less typing and so as not to interfere with other functions use test_microsim

    # Note: the following is a useul way to get relevant info about the individuals
    # m.individuals.loc[:, ["ID", "PID", "HID", "area", ColumnNames.DISEASE_STATUS, "MSOA_Cases", "HID_Cases"]]

    # Set the hazard-related parameters.

    # As we don't specify them when the tests are set up, they should be empty dictionaries
    assert not m.hazard_location_multipliers
    assert not m.hazard_individual_multipliers

    # Manually create some hazards for individuals and locationsas per the parameters file
    m.hazard_individual_multipliers["presymptomatic"] = 1.0
    m.hazard_individual_multipliers["asymptomatic"] = 2.0
    m.hazard_individual_multipliers["symptomatic"] = 3.0
    for act in ColumnNames.Activities.ALL:
        m.hazard_location_multipliers[act] = 1.0

    # Step 0 (initialisation):

    # Everyone should start without the disease (they will have been assigned a status as part of initialisation)
    m.individuals[ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SUSCEPTIBLE

    #
    # Person 1: lives with one other person (p2). Both people spend all their time at home doing nothing else
    #
    p1 = 0
    p2 = 1

    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.PRESYMPTOMATIC  # Give p1 the disease
    for p in [p1, p2]:  # Set their activity durations to 0 except for home
        for name, activity in m.activity_locations.items():
            m.individuals.at[p, f"{name}{ColumnNames.ACTIVITY_DURATION}"] = 0.0
        m.individuals.at[p, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] = 1.0

    m.step()

    # Check the disease has spread to the house with a multiplier of 1.0, but nowhere else
    _check_hazard_spread(p1, p2, m.individuals, m.households, 1.0)

    # If the person is asymptomatic, we said the hazard should be doubled, so the risk should be doubled
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.ASYMPTOMATIC  # Give p1 the disease
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SUSCEPTIBLE  # Make sure p2 is clean

    m.step()
    _check_hazard_spread(p1, p2, m.individuals, m.households, 2.0)

    # And for symptomatic we said 3.0
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC  # Give p1 the disease
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SUSCEPTIBLE  # Make sure p2 is clean

    m.step()
    _check_hazard_spread(p1, p2, m.individuals, m.households, 3.0)


    # But if they both get sick then double danger and risk)
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC
    m.step()
    _check_hazard_spread(p1, p2, m.individuals, m.households, 6.0)

    #
    # Now see if the hazards for locations work. Check houses and schools
    #

    # Both people are symptomatic. And double the hazard for home. So in total the new risk should
    # be 3 * 2 * 5 = 30
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC
    m.hazard_location_multipliers[ColumnNames.Activities.HOME] = 5.0

    m.step()
    _check_hazard_spread(p1, p2, m.individuals, m.households, 30.0)


    # Check for school as well. Now give durations for home and school as 0.5. Make them asymptomatic so the additional
    # hazard is 2.0 (set above). And make the risks for home 5.35 and for school 2.9.

    # Make sure all *other* individuals go to a different school (school 1), then make p1 and p2 go to the same school
    # (school 0) below
    # (annoying apply is because pandas doesn't like a list being assigned to a value in a cell)
    m.individuals[f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_VENUES}"] = \
        m.individuals.loc[:, f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_VENUES}"].apply(lambda x: [1])
    m.individuals.loc[[p1, p2], f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_VENUES}"] = \
        m.individuals.loc[[p1, p2], f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_VENUES}"].apply(lambda x: [0])
    # All school flows need to be 1 (don't want the people to go to more than 1 school
    m.individuals[f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_FLOWS}"] = \
        m.individuals.loc[:, f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_VENUES}"].apply(lambda x: [1.0])

    for p in [p1, p2]:  # Set their activity durations to 0.5 for home and school
        for name, activity in m.activity_locations.items():
            m.individuals.at[p, f"{name}{ColumnNames.ACTIVITY_DURATION}"] = 0.0
        m.individuals.at[p, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] = 0.5
        m.individuals.at[p, f"{ColumnNames.Activities.PRIMARY}{ColumnNames.ACTIVITY_DURATION}"] = 0.5
    # Make them asymptomatic
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.ASYMPTOMATIC
    m.individuals.loc[p2, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.ASYMPTOMATIC
    # Set hazards for home and school
    m.hazard_location_multipliers[ColumnNames.Activities.HOME] = 5.35
    m.hazard_location_multipliers[ColumnNames.Activities.PRIMARY] = 2.9

    m.step()

    # Can't use _check_hazard_spread because it assumes only one activity (HOME)
    # Current risks are:
    # For home. 2 people * 2.0 asymptomatic hazard * 0.5 duration * 5.35 HOME risk = 10.7
    # For school. 2 people * 2.0 asymptomatic hazard * 0.5 duration * 2.9 PRIMARY risk = 5.8
    # Total risk for individuals: 10.7*0.5 + 5.8*0.5 = 8.25

    # Individuals
    for p in [p1, p2]:
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 8.25
    for p in range(2, len(m.individuals)):
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 0.0

    # Households
    assert m.households.at[0, ColumnNames.LOCATION_DANGER] == 10.7
    # (the self.households dataframe should be the same as the one stored in the activity_locations)
    assert m.activity_locations[ColumnNames.Activities.HOME]._locations.at[0, ColumnNames.LOCATION_DANGER] == 10.7
    for h in range(1, len(m.households)):  # all others are 0
        assert m.households.at[h, ColumnNames.LOCATION_DANGER] == 0.0

    # Schools
    assert m.activity_locations[ColumnNames.Activities.PRIMARY]._locations.at[0, ColumnNames.LOCATION_DANGER] == 5.8
    for h in range(1, len( m.activity_locations[ColumnNames.Activities.PRIMARY]._locations)):  # all others are 0
        assert m.activity_locations[ColumnNames.Activities.PRIMARY]._locations.at[h, ColumnNames.LOCATION_DANGER] == 0.0

    print("End of test hazard multipliers")


def _check_hazard_spread(p1, p2, individuals, households, risk):
    """Checks how the disease is spreading. To save code repetition in test_hazard_multipliers"""
    for p in [p1, p2]:
        assert individuals.at[p, ColumnNames.CURRENT_RISK] == risk
    for p in range(2, len(individuals)):
        assert individuals.at[p, ColumnNames.CURRENT_RISK] == 0.0
    assert households.at[0, ColumnNames.LOCATION_DANGER] == risk
    for h in range(1, len(households)):  # all others are 0
        assert households.at[h, ColumnNames.LOCATION_DANGER] == 0.0



def test_step(test_microsim):
    """
    Test the step method. This is the main test of the model. Simulate a deterministic run through and
    make sure that the model runs as expected.

    Only thing it doesn't do is check for retail, shopping, etc., that danger and risk increase by the correct
    amount. It just checks they go above 0 (or not). It does do that more precise checks for home activities though.

    :param test_microsim: This is a pointer to the initialised model. Dummy data will have been read in,
    but no stepping has taken place yet."""
    m = copy.deepcopy(test_microsim)  # For less typing and so as not to interfere with other functions use test_microsim

    # Note: the following is a useul way to get relevant info about the individuals
    # m.individuals.loc[:, ["ID", "PID", "HID", "area", ColumnNames.DISEASE_STATUS, "MSOA_Cases", "HID_Cases"]]

    # Step 0 (initialisation):

    # Everyone should start without the disease (they will have been assigned a status as part of initialisation)
    m.individuals[ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SUSCEPTIBLE

    #
    # Person 1: lives with one other person (p2). Both people spend all their time at home doing nothing else
    #
    p1 = 0
    p2 = 1

    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC  # Give them the disease
    for p in [p1, p2]:  # Set their activity durations to 0
        for name, activity in m.activity_locations.items():
            m.individuals.at[p, f"{name}{ColumnNames.ACTIVITY_DURATION}"] = 0.0
        m.individuals.at[p, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] = 1.0  # Spend all their time at home

    m.step()

    # Check the disease has spread to the house but nowhere else
    for p in [p1, p2]:
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 1.0
    for p in range(2, len(m.individuals)):
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 0.0
    assert m.households.at[0, ColumnNames.LOCATION_DANGER] == 1.0
    for h in range(1, len(m.households)):  # all others are 0
        assert m.households.at[h, ColumnNames.LOCATION_DANGER] == 0.0

    m.step()

    # Risk and danger stay the same (it does not cumulate over days)
    for p in [p1, p2]:
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 1.0
    for p in range(2, len(m.individuals)):
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 0.0
    m.households.at[0, ColumnNames.LOCATION_DANGER] == 1.0
    for h in range(1, len(m.households)):
        assert m.households.at[h, ColumnNames.LOCATION_DANGER] == 0.0

    # If the infected person doesn't go home (in this test they do absolutely nothing) then danger and risks should go
    # back to 0
    m.individuals.at[p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] = 0.0
    m.step()
    for p in range(len(m.individuals)):
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 0.0
    for h in range(0, len(m.households)):
        assert m.households.at[h, ColumnNames.LOCATION_DANGER] == 0.0

    # But if they both get sick then they should be 2.0 (double danger and risk)
    m.individuals.loc[p1:p2, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC  # Give them the disease
    m.individuals.at[p1, f"{ColumnNames.Activities.HOME}{ColumnNames.ACTIVITY_DURATION}"] = 1.0  # Make the duration normal again
    m.step()
    for p in [p1, p2]:
        assert m.individuals.at[p, ColumnNames.CURRENT_RISK] == 2.0
    assert m.households.at[0, ColumnNames.LOCATION_DANGER] == 2.0
    for h in range(1, len(m.households)):  # All other houses are danger free
        m.households.at[h, ColumnNames.LOCATION_DANGER] == 0.0

    #
    # Now see what happens when one person gets the disease and spreads it to schools, shops and work
    #
    del p1, p2
    p1 = 4  # The infected person is index 1
    # Make everyone better except for that one person
    m.individuals[ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SUSCEPTIBLE
    m.individuals.loc[p1, ColumnNames.DISEASE_STATUS] = ColumnNames.DiseaseStatuses.SYMPTOMATIC
    # Assign everyone equal time doing all activities
    for name, activity in m.activity_locations.items():
        m.individuals[f"{name}{ColumnNames.ACTIVITY_DURATION}"] = 1.0 / len(m.activity_locations)

    m.step()

    # Now check that the danger has propagated to locations and risk to people
    # TODO Also check that the total risks and danger scores sum correctly
    for name, activity in m.activity_locations.items():
        # Indices of the locations where this person visited
        visited_idx = m.individuals.at[p1, f"{name}{ColumnNames.ACTIVITY_VENUES}"]
        not_visited_idx = list(set(range(len(activity._locations))) - set(visited_idx))
        # Dangers should be >0.0 (or not if the person didn't visit there)
        assert False not in list(activity._locations.loc[visited_idx, "Danger"].values > 0)
        assert False not in list(activity._locations.loc[not_visited_idx, "Danger"].values == 0)
        # Individuals should have an associated risk
        for index, row in m.individuals.iterrows():
            for idx in visited_idx:
                if idx in row[f"{name}{ColumnNames.ACTIVITY_VENUES}"]:
                    assert row[ColumnNames.CURRENT_RISK] > 0
                    # Note: can't check if risk is equal to 0 becuase it might come from another activity

    print("End of test step")


# ********************************************************
# Other (unit) tests
# ********************************************************

def _get_rand(microsim, N=100):
    """Get a random number using the Microsimulation object's random number generator"""
    for _ in range(N):
        microsim.random.random()
    return microsim.random.random()


def test_random():
    """
    Checks that random classes are produce different (or the same!) numbers when they should do
    :return:
    """
    m1 = Microsim(**microsim_args, read_data=False)
    m2 = Microsim(**microsim_args, random_seed=2.0, read_data=False)
    m3 = Microsim(**microsim_args, random_seed=2.0, read_data=False)

    # Genrate a random number from each model. The second two numbers should be the same
    r1, r2, r3 = [_get_rand(x) for x in [m1, m2, m3]]

    assert r1 != r2
    assert r2 == r3

    # Check that this still happens even if they are executed in pools.
    # Create a large number of microsims and check that all random numbers are unique
    pool = multiprocessing.Pool()
    num_reps = 1000
    m = [Microsim(**microsim_args, read_data=False) for _ in range(num_reps)]
    r = pool.map(_get_rand, m)
    assert len(r) == len(set(r))


def test_extract_msoas_from_indiviuals():
    """Check that a list of areas can be successfully extracted from a DataFrame of indviduals"""
    individuals = pd.DataFrame(data={"area": ["C", "A", "F", "A", "A", "F"]})
    areas = Microsim.extract_msoas_from_indiviuals(individuals)
    assert len(areas) == 3
    # Check the order is correct too
    assert False not in [x == y for (x, y) in zip(areas, ["A", "C", "F"])]


@pytest.mark.skip(reason="No longer running this test as the functionality to select by study area has been removed")
def test_check_study_area():
    all_msoa_list = ["C", "A", "F", "B", "D", "E"]
    individuals = pd.DataFrame(
        data={"PID": [1, 2, 3, 4, 5, 6], "HID": [1, 1, 2, 2, 2, 3], "area": ["B", "B", "A", "A", "A", "D"],
              "House_OA": ["B", "B", "A", "A", "A", "D"]})
    households = pd.DataFrame(data={"HID": [1, 2, 3], "area": ["B", "A", "D"]})

    with pytest.raises(Exception):
        # Check that it catches duplicate areas
        assert Microsim.check_study_area(all_msoa_list, ["A", "A", "B"], individuals, households)
        assert Microsim.check_study_area(all_msoa_list + ["A"], ["A", "B"], individuals, households)
        # Check that it catches subset areas that aren't in the whole dataset
        assert Microsim.check_study_area(all_msoa_list, ["A", "B", "G"], individuals, households)

    # Should return whole dataset if no subset is provided
    assert Microsim.check_study_area(all_msoa_list, None, individuals, households)[0] == all_msoa_list
    assert Microsim.check_study_area(all_msoa_list, [], individuals, households)[0] == all_msoa_list

    with pytest.raises(Exception):
        # No individuals in area "E" so this should fail:
        assert Microsim.check_study_area(all_msoa_list, ["A", "B", "E"], individuals, households)

    # Correctly subset and remove individuals
    x = Microsim.check_study_area(all_msoa_list, ["A", "D"], individuals, households)
    assert x[0] == ["A", "D"]  # List of areas
    assert list(x[1].PID.unique()) == [3, 4, 5, 6]  # List of individuals
    assert list(x[2].HID.unique()) == [2, 3]  # List of households


def test__add_location_columns():
    df = pd.DataFrame(data={"Name": ['a', 'b', 'c', 'd']})
    with pytest.raises(Exception):  # Should fail if lists are wrong length
        Microsim._add_location_columns(df, location_names=["a", "b"], location_ids=None)
        Microsim._add_location_columns(df, location_names=df.Name, location_ids=[1, 2])
    with pytest.raises(TypeError):  # Can't get the length of None
        Microsim._add_location_columns(df, location_names=None)

    # Call the function
    x = Microsim._add_location_columns(df, location_names=df.Name)
    assert x is None  # Function shouldn't return anything. Does things inplace
    # Default behaviour is just add columns
    assert False not in (df.columns.values == ["Name", "ID", "Location_Name", "Danger"])
    assert False not in list(df.Location_Name == df.Name)
    assert False not in list(df.ID == range(0, 4))
    assert False not in list(df.index == range(0, 4))
    # Adding columns again shouldn't change anything
    Microsim._add_location_columns(df, location_names=df.Name)
    assert False not in (df.columns.values == ["Name", "ID", "Location_Name", "Danger"])
    assert False not in list(df.Location_Name == df.Name)
    assert False not in list(df.ID == range(0, 4))
    assert False not in list(df.index == range(0, 4))
    # See what happens if we give it IDs
    Microsim._add_location_columns(df, location_names=df.Name, location_ids=[5, 7, 10, -1])
    assert False not in (df.columns.values == ["Name", "ID", "Location_Name", "Danger"])
    assert False not in list(df.ID == [5, 7, 10, -1])
    assert False not in list(df.index == range(0, 4))  # Index shouldn't change
    # Shouldn't matter if IDs are Dataframes or Series
    Microsim._add_location_columns(df, location_names=pd.Series(df.Name))
    assert False not in list(df.Location_Name == df.Name)
    assert False not in list(df.index == range(0, 4))  # Index shouldn't change
    Microsim._add_location_columns(df, location_names=df.Name, location_ids=np.array([5, 7, 10, -1]))
    assert False not in list(df.ID == [5, 7, 10, -1])
    assert False not in list(df.index == range(0, 4))  # Index shouldn't change
    # Set a weird index, the function should replace it with the row number
    df = pd.DataFrame(data={"Name": ['a', 'b', 'c', 'd'], "Col2": [4, -6, 8, 1.4]}, )
    df.set_index("Col2")
    Microsim._add_location_columns(df, location_names=df.Name)
    assert False not in list(df.ID == range(0, 4))
    assert False not in list(df.index == range(0, 4))

    # TODO dest that the _add_location_columns function correctly adds the required standard columns
    # to a locaitons dataframe, and does appropriate checks for correct lengths of input lists etc.


def test__normalise():
    # TODO test the 'decimals' argument too.
    # Should normalise so that the input list sums to 1
    # Fail if aa single number is given
    for l in [2, 1]:
        with pytest.raises(Exception):
            Microsim._normalise(l)

    # 1-item lists should return [1.0]
    for l in [[0.1], [5.3]]:
        assert Microsim._normalise(l) == [1.0]

    # If numbers are the same (need to work out why these tests fail,the function seems OK)
    # for l in [ [2, 2], [0, 0], [-1, -1], [1, 1] ]:
    #    assert Microsim._normalise(l) == [0.5, 0.5]

    # Other examples
    assert Microsim._normalise([4, 6]) == [0.4, 0.6]
    assert Microsim._normalise([40, 60]) == [0.4, 0.6]
    assert Microsim._normalise([6, 6, 6, 6, 6]) == [0.2, 0.2, 0.2, 0.2, 0.2]

def test_find_new_directory():
    """
    A unit test for the _find_new_directory() function
    """

    data_dir = os.path.join(test_dir,'dummy_data','output')

    scenario_dir = 'test_output'

    Microsim._find_new_directory(data_dir, scenario_dir)

    assert os.path.isdir(os.path.join(data_dir, scenario_dir))

    # test if function creates a new directory with _1 suffix if directory exists
    Microsim._find_new_directory(data_dir, "test_dir")

    assert os.path.isdir(os.path.join(data_dir, "test_dir_1"))

def test_find_new_directory_fails():
    """
    A unit test to check _find_new_directory() function fails 
    """

    data_dir = os.path.join(test_dir,'dummy_data','output')

    with pytest.raises(FileExistsError):
        Microsim._find_new_directory(data_dir, "existing_dir")