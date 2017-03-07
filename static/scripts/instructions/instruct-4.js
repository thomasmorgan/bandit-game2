$(document).ready(function() {
    $("#next-button").click(function() {
        allow_exit();
        go_to_page("instructions/instruct-5");
    });
    $("#back-button").click(function() {
        allow_exit();
        go_to_page("instructions/instruct-3");
    });
    reqwest({
        url: "/num_trials",
        method: 'get',
        success: function (resp) {
            trials_per_network = resp.n_trials;
            networks = resp.experiment_repeats;
            $("#number_of_trials").html(trials_per_network);
            $("#number_of_rounds").html(networks);
        }
    });
});
