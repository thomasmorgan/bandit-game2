var tiles_checked = 0;
var decided = false;
var trials_per_network;
var trial_in_this_network = 0;
var round_number = 0;
var number_of_rounds;
var available_bandit_names = ["Afghanistan", "Albania", "Argentina", "Australia", "Austria", "Bangladesh", "Belgium", "Botswana", "Brasil", "Bulgaria", "Burundi", "Canada", "Chad", "Chile", "China", "Colombia", "Costa Rica", "Croatia", "Denmark", "Ecuador", "Egypt", "England", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Germany", "Ghana", "Greece", "Greenland", "Guatemala", "Holland", "India", "Iran", "Ireland", "Italy", "Japan", "Laos", "Libya", "Madagascar", "Mali", "Mexico", "Mongolia", "Morocco", "Mozambique", "Myanmar", "Nepal", "New Zealand", "Nigeria", "Norway", "Pakistan", "Papua New Guinea", "Poland", "Portugal", "Romania", "Russia", "Scotland", "Senegal", "Sierra Leone", "South Korea", "Spain", "Sri Lanka", "Sweden", "Thailand", "The United States", "Tonga", "Tunisia", "Turkey", "Turkmenistan", "Ukraine", "Wales", "Yemen"];
var bandit_names;
var lock = false;
bandit_mapping = [];

$(document).ready(function() {
    get_num_trials();
    get_p_move();
    create_agent();
});

// get all the details to correctly present the trial number bar
get_num_trials = function() {
    reqwest({
        url: "/experiment/n_trials",
        method: 'get',
        success: function (resp) {
            trials_per_network = resp.n_trials;
            reqwest({
                url: "experiment/experiment_repeats",
                method: 'get',
                success: function (resp) {
                    number_of_rounds = resp.experiment_repeats;
                    prepare_trial_info_text();
                }
            });
        }
    });
};

// get all the details to correctly present the trial number bar
get_p_move = function() {
    reqwest({
        url: "/experiment/p_move",
        method: 'get',
        success: function (resp) {
            p_change = resp.p_move;
        }
    });
};

// make a new node
create_agent = function() {
    reqwest({
        url: "/node/" + participant_id,
        method: 'post',
        type: 'json',
        success: function (resp) {
            my_node_id = resp.node.id;
            my_network_id = resp.node.network_id;
            prepare_for_new_round();
            get_genes();
        },
        error: function (err) {
            console.log(err);
            err_response = JSON.parse(err.response);
            if (err_response.hasOwnProperty('html')) {
                $('body').html(err_response.html);
            } else {
                allow_exit();
                go_to_page("questionnaire");
            }
        }
    });
};

prepare_for_new_round = function() {
    round_number = round_number + 1;
    trial_in_this_network = 0;
    bandit_memory = [];
};

// what is my memory and curiosity?
get_genes = function() {
    reqwest({
        url: "/node/" + my_node_id + "/infos",
        method: 'get',
        type: 'json',
        data: {
            info_type: "Gene"
        },
        success: function (resp) {
            infos = resp.infos;
            for (i = 0; i < infos.length; i++) {
                info = infos[i];
                if (info.type == "curiosity_gene") {
                    my_curiosity = info.contents;
                } else {
                    my_memory = info.contents;
                }
            }
            get_num_bandits();
        }
    });
};

// how many bandits are there?
get_num_bandits = function() {
    reqwest({
        url: "/experiment/n_bandits",
        method: 'get',
        type: 'json',
        success: function (resp) {
            num_bandits = resp.n_bandits;
            bandit_names = [];
            for (i = 0; i < num_bandits; i++) {
                bandit_names.push("a");
            }
            get_num_arms();
        }
    });
};

// how many arms do the bandits have?
get_num_arms = function() {
    reqwest({
        url: "/experiment/num_arms",
        method: 'get',
        type: 'json',
        success: function (resp) {
            num_arms = resp.num_arms;
            pick_a_bandit();
        }
    });
};

// pick my current bandit
pick_a_bandit = function () {
    // pick a bandit
    current_bandit = Math.floor(Math.random()*num_bandits);

    // do you remember them
    if (my_memory > 0) {
        remember_bandit = $.inArray(current_bandit, bandit_memory.slice(-my_memory)) > -1;
    } else {
        remember_bandit = false;
    }

    // if you don't remember them pick a new country for them and re-map the arms
    if (remember_bandit === false) {
        index = Math.floor(Math.random()*available_bandit_names.length);
        bandit_names[current_bandit] = available_bandit_names[index];
        available_bandit_names.splice(index, 1);
        bandit_mapping[current_bandit] = new_mapping(num_arms);
    }

    // load the bandits name and image
    current_bandit_name = bandit_names[current_bandit];
    name_of_image = '<img src="/static/images/locations/' + current_bandit_name + '/flag.png"/>';
    $("#flag_div").html(name_of_image);

    // which arm is the bandits good arm?
    reqwest({
        url: "/good_arm/" + my_network_id + "/" + current_bandit,
        method: 'get',
        type: 'json',
        success: function (resp) {
            good_arm = resp.good_arm;
            prepare_for_trial();
        }
    });
};

prepare_for_trial = function() {
    // stochastically move the treasure
    for (i = 0; i < num_bandits; i++) {
        if (Math.random() < p_change) {
            bandit_mapping[i] = new_mapping(num_arms);
        }
    }

    // update ui
    trial_in_this_network = trial_in_this_network + 1;
    prepare_trial_info_text();

    
    for (i = 0; i < num_arms; i++) {
        name_of_tile = "#tile_" + (i+1);
        name_of_image = '<img src="/static/images/locations/' + current_bandit_name + '/' + (i+1) + '.png" onClick="check_tile(' + (i+1) + ')"/>';
        $(name_of_tile).html(name_of_image);
    }
    $("#mini_title").html("<p>You are looking for treasure in <b>" + current_bandit_name + "</b></p>");
    $("#instructions").html("<p><font color='green'><b>You can check " + my_curiosity + " locations</b></font></p>");
    $("#ready_button").prop("disabled", false);

    // reset check counter
    tiles_checked = 0;
};

prepare_trial_info_text = function() {
    $("#trial_number").html(trial_in_this_network);
    $("#number_of_trials").html(trials_per_network);
    $("#round_number").html(round_number);
    $("#number_of_rounds").html(number_of_rounds);
};

// look under a tile
check_tile = function (tile) {
    if (lock === false & tiles_checked < my_curiosity) {
        lock = true;
        tiles_checked = tiles_checked + 1;
        save_pull(tile, true);
        name_of_tile = "#tile_" + tile;
        if (bandit_mapping[current_bandit][tile-1] == good_arm) {
            name_of_image = '<img src="/static/images/treasure.png"/>';
        } else {
            name_of_image = '<img src="/static/images/no.png"/>';
        }
        $(name_of_tile).html(name_of_image);
        lock = false;
    }
};

// prepare the tiles for the final decision
prepare_for_decision = function () {
    $("#ready_button").prop("disabled", true);
    decided = false;
    $("#instructions").html("<p><b>Please make your final choice.</b></p>");
    lock = true;
    for (i = 0; i < num_arms; i++) {
        name_of_tile = "#tile_" + (i+1);
        name_of_image = '<img src="/static/images/locations/' + current_bandit_name + '/' + (i+1) + '.png" onClick="choose_tile(' + (i+1) + ')"/>';
        $(name_of_tile).html(name_of_image);
    }
    lock = false;
};

// commit to a particular tile 
choose_tile = function (tile) {
    if (lock === false & decided === false) {
        lock = true;
        decided = true;
        $("#instructions").html("<p>Your decision is being saved, please wait...</p>");
        bandit_memory.push(current_bandit);
        save_pull(tile, false);
        name_of_tile = "#tile_" + tile;
        name_of_image = '<img src="/static/images/dot.png"/>';
        $(name_of_tile).html(name_of_image);
        setTimeout(function() {
            advance_to_next_trial();
        }, 800);
        lock = false;
    }
};

save_pull = function (tile, check) {
    reqwest({
        url: "/info/" + my_node_id,
        method: 'post',
        type: 'json',
        data: {
            contents: bandit_mapping[current_bandit][tile-1],
            info_type: "Pull",
            property1: check, // check
            property2: current_bandit, // bandit_id
            property3: remember_bandit, // remembered
            property4: tile,
            property5: trial_in_this_network
        },
    });
};

advance_to_next_trial = function () {
    if (trial_in_this_network == trials_per_network) {
        reqwest({
            url: "/node/" + my_node_id + "/calculate_fitness",
            method: "get",
            type: 'json',
            success: function (resp) {
                show_warning();
                create_agent();
            },
            error: function (err) {
                console.log(err);
                err_response = JSON.parse(err.response);
                $('body').html(err_response.html);
            }
        });
    } else {
        travel();
        pick_a_bandit();
    }
};

travel = function () {
    $("#table_div").hide();
    $("#warning_div").hide();
    $("#travel_div").show();
    setTimeout(function() {
        $("#travel_div").hide();
        $("#table_div").show();
    }, 1200);
};

show_warning = function () {
    $("#table_div").hide();
    $("#travel_div").hide();
    $("#warning_div").show();
    setTimeout(function() {
        $("#warning_div").hide();
        $("#table_div").show();
    }, 3500);
};

new_mapping = function (max) {
    return shuffle(Array.apply(null, Array(max)).map(function (_, i) {return i+1;}));
};

shuffle = function(a) {
    var j, x, i;
    for (i = a.length; i; i -= 1) {
        j = Math.floor(Math.random() * i);
        x = a[i - 1];
        a[i - 1] = a[j];
        a[j] = x;
    }
    return a;
};