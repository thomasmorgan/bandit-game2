// stop people leaving the page
window.onbeforeunload = function() {
    return "Warning: the study is not yet finished. " +
    "Closing the window, refreshing the page or navigating elsewhere " +
    "might prevent you from finishing the experiment.";
};

// allow actions to leave the page
allow_exit = function() {
    window.onbeforeunload = function() {};
};

// go back to psiturk
return_to_psiturk_server = function() {
    reqwest({
        url: "/ad_address/" + mode + '/' + hit_id,
        method: 'get',
        type: 'json',
        success: function (resp) {
            console.log(resp.address);
            allow_exit();
            window.location = resp.address + "?uniqueId=" + uniqueId;
        },
        error: function (err) {
            console.log(err);
            err_response = JSON.parse(err.response);
            $('body').html(err_response.html);
        }
    });
};

// make a new participant
create_participant = function() {
    reqwest({
        url: "/participant/" + worker_id + '/' + hit_id + '/' + assignment_id,
        method: 'post',
        type: 'json'
    });
};